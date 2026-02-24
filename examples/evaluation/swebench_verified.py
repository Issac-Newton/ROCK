import shlex
import sys
from pathlib import Path

from examples.evaluation.common import load_task_config, parse_swebench_result, setup_test_env
from examples.evaluation.constants import SWE_PROMPT_TEMPLATE, global_agent_timeout_sec, global_test_timeout_sec
from rock.actions.sandbox.request import CreateBashSessionRequest
from rock.actions.sandbox.response import Observation
from rock.logger import init_logger
from rock.sdk.sandbox.client import RunMode, Sandbox
from rock.sdk.sandbox.config import SandboxConfig

logger = init_logger(__name__)


async def start_sandbox(swe_task_name: str) -> Sandbox:
    """Start a sandbox instance for evaluation."""
    acr_url = "rock-registry.ap-southeast-1.cr.aliyuncs.com/slimshetty/swebench-verified"
    # acr_url = (
    #     "rock-registry.cn-hangzhou.cr.aliyuncs.com/slimshetty/swebench-verified"
    #     if swe_task_name not in task_in_sg
    #     else "rock-registry.ap-southeast-1.cr.aliyuncs.com/slimshetty/swebench-verified"
    # )
    image = f"{acr_url}:sweb.eval.x86_64.{swe_task_name}"
    config = SandboxConfig(
        image=image,
        cluster="sg-a",
        xrl_authorization="t-f8276d9f7afd4b38",
        user_id="400231",
        experiment_id="swebench-verified-test",
        base_url="http://xrl.alibaba-inc.com",
        auto_clear_seconds=3600,
        startup_timeout=500,
    )
    sandbox = Sandbox(config)
    await sandbox.start()
    return sandbox


async def install_iflow_agent(sandbox: Sandbox, config_path: str) -> None:
    """Install iflow agent in sandbox."""
    await sandbox.agent.install(config=config_path)
    logger.info("iflow agent installed successfully.")


async def run_swe_evaluation(sandbox: Sandbox, task_dir: Path, task_name: str, question: str, config_path: str) -> bool:
    """Run SWE evaluation on the sandbox."""
    # 1. Install agent
    await sandbox.agent.install(config=config_path)

    # 2. Prepare prompt
    prompt = SWE_PROMPT_TEMPLATE.format(workdir=sandbox.agent.config.project_path, question=question)
    result = await sandbox.agent.run(prompt)
    logger.info(f"Task name: {task_name}, sandbox id : {sandbox.sandbox_id}, Agent run result: {result}")

    # # 3. Install uv
    uv_install_script_commands = [
        "wget https://github.com/astral-sh/uv/releases/download/0.10.5/uv-x86_64-unknown-linux-gnu.tar.gz",
        "tar -xzf uv-x86_64-unknown-linux-gnu.tar.gz --strip-components=1 -C /usr/local/bin",
    ]
    session_name = "swe-evaluation"
    await sandbox.create_session(
        CreateBashSessionRequest(
            session=session_name,
            env_enable=True,
            env={"UV_PYTHON_INSTALL_MIRROR": "https://registry.npmmirror.com/-/binary/python-build-standalone"},
        )
    )
    for uv_install_script in uv_install_script_commands:
        result = await sandbox.arun(
            uv_install_script, session=session_name, mode=RunMode.NOHUP, wait_timeout=global_agent_timeout_sec
        )

    logger.info(f"Task name: {task_name}, sandbox id : {sandbox.sandbox_id}, UV install result: {result}")

    # 4. Setup upload test files
    test_file_dir = task_dir / "tests"
    sandbox_test_dir = "/tests"
    is_success = await setup_test_env(sandbox, test_file_dir, sandbox_test_dir, task_dir / "run-tests.sh")
    if not is_success:
        logger.error("Failed to setup test environment")
        return False

    # 5. Run tests
    logger.info(f"Task name: {task_name}, sandbox id : {sandbox.sandbox_id}, Start to run tests")
    test_scripts = sandbox_test_dir + "/run-tests.sh"
    run_tests_command = f"sh -c {shlex.quote('bash ' + test_scripts)}"
    resp: Observation = await sandbox.arun(
        run_tests_command, session=session_name, mode=RunMode.NOHUP, wait_timeout=global_test_timeout_sec
    )
    logger.info(f"Task name: {task_name}, sandbox id : {sandbox.sandbox_id}, Run tests result: {resp}")

    # 6. Parse results
    resolve_result = parse_swebench_result(resp.output)
    logger.info(f"Task name: {task_name}, sandbox id : {sandbox.sandbox_id}, is_resolved: {resolve_result}")
    return resolve_result


async def run_single_task(task_dir: Path, config_path: str, semaphore) -> dict:
    """Run evaluation for a single task."""
    async with semaphore:
        task_name = task_dir.name
        logger.info(f"Starting evaluation for task: {task_name}")

        try:
            # Load task configuration
            task_config = await load_task_config(task_dir)
            question = task_config.get("instruction", "")

            if not question:
                logger.error(f"No instruction found in task.yaml for {task_name}")
                return {"task_name": task_name, "status": "failed", "error": "No instruction in task.yaml"}

            # Start sandbox
            sandbox = await start_sandbox(task_name)

            try:
                # Run evaluation
                resolve_result = await run_swe_evaluation(sandbox, task_dir, task_name, question, config_path)
                logger.info(f"Completed evaluation for task: {task_name}")
                return {
                    "task_name": task_name,
                    "sandbox_id": sandbox.sandbox_id,
                    "status": "success",
                    "resolved": resolve_result,
                }
            except Exception as e:
                logger.error(f"Error running evaluation for {task_name}: {e}")
                return {"task_name": task_name, "sandbox_id": sandbox.sandbox_id, "status": "failed", "error": str(e)}
            # finally:
            #     await sandbox.stop()
        except Exception as e:
            logger.error(f"Error loading task config for {task_name}: {e}")
            return {"task_name": task_name, "status": "failed", "error": str(e)}


async def run_parallel_evaluations(tasks_dir: Path, parallel_num: int, config_path: str) -> list:
    """Run evaluations for all tasks in parallel."""
    import asyncio

    # Get all task directories
    task_dirs = [d for d in tasks_dir.iterdir() if d.is_dir() and (d / "task.yaml").exists()]

    if not task_dirs:
        logger.error(f"No valid task directories found in {tasks_dir}")
        return []

    logger.info(f"Found {len(task_dirs)} tasks to evaluate")
    logger.info(f"Running with parallelism: {parallel_num}")

    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(parallel_num)

    # Run all tasks
    tasks = [run_single_task(task_dir, config_path, semaphore) for task_dir in task_dirs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return results


if __name__ == "__main__":
    import asyncio

    if len(sys.argv) < 2:
        print("Error: Tasks directory must be provided as a command-line argument.")
        print("Usage: python swebench_verified.py <tasks_dir> [parallel_num] [config_path]")
        print("Example: python swebench_verified.py ./swebench-verified 2 iflow_swe_config.yaml")
        sys.exit(1)

    cur_dir = Path(__file__).resolve().parent
    tasks_dir = Path(sys.argv[1])
    parallel_num = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    config_path = sys.argv[3] if len(sys.argv) > 3 else f"{cur_dir}/iflow_swe_config.yaml"

    if not tasks_dir.exists():
        print(f"Error: Tasks directory does not exist: {tasks_dir}")
        sys.exit(1)

    print("Starting SWE evaluation")
    print(f"Tasks directory: {tasks_dir}")
    print(f"Parallel number: {parallel_num}")
    print(f"Config path: {config_path}")

    result_file = open("result-sandbox-failed.json", "w")

    async def main():
        results = await run_parallel_evaluations(tasks_dir, parallel_num, config_path)
        print(f"all tasks completed, result is {results}")
        import json

        json.dump(results, result_file, indent=4)
        result_file.close()

        # Print summary
        print("\n" + "=" * 80)
        print("EVALUATION SUMMARY")
        print("=" * 80)

        success_count = sum(
            1 for r in results if isinstance(r, dict) and r.get("status") == "success" and r.get("resolved") is True
        )
        failed_count = len(results) - success_count

        print(f"Total tasks: {len(results)}")
        print(f"Successful: {success_count}")
        print(f"Failed: {failed_count}")

        if failed_count > 0:
            print("\nFailed tasks:")
            for r in results:
                if isinstance(r, dict) and r.get("status") == "failed":
                    print(f"  - {r['task_name']}: {r.get('error', 'Unknown error')}")

        print("=" * 80)

    asyncio.run(main())
