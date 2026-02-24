import re
import shlex
import sys
from pathlib import Path

from examples.evaluation.common import load_task_config
from examples.evaluation.constants import SWE_PROMPT_TEMPLATE, global_agent_timeout_sec, global_test_timeout_sec
from examples.evaluation.parser.base_parser import UnitTestStatus
from examples.evaluation.parser.swebench_parser import SWEBenchParser
from rock.actions.sandbox.request import Action, CreateBashSessionRequest
from rock.logger import init_logger
from rock.sdk.sandbox.client import RunMode, Sandbox
from rock.sdk.sandbox.config import SandboxConfig

logger = init_logger(__name__)

test_result_parser = SWEBenchParser()


def is_resolved(parser_results: dict[str, UnitTestStatus] | None) -> bool:
    if parser_results is None:
        return False

    return all(result == UnitTestStatus.PASSED for result in parser_results.values())


async def _setup_test_env(sandbox: Sandbox, test_folder: Path, run_tests_scripts: Path) -> bool:
    test_dir = "/tests"
    res = await sandbox.fs.upload_dir(test_folder, test_dir)
    if res.exit_code != 0:
        logger.error(f"Failed to upload test folder: {res}")
        return False

    res = await sandbox.upload_by_path(run_tests_scripts, f"{test_dir}/{run_tests_scripts.name}")
    if not res.success:
        logger.error(f"Failed to upload run-tests.sh: {res}")
        return False

    return True


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


def _extract_pid(output: str) -> str:
    # 统一换行并分割
    lines = output.splitlines()
    if not lines:
        return ""
    last_line = lines[-1].strip()
    match = re.match(r"\[\d+\]\s+(\d+)", last_line)
    return match.group(1) if match else ""


async def run_command_with_timeout(
    sandbox: Sandbox, command: str, session_name: str, timeout_sec: int, output_file: str
) -> str:
    """Run a command in sandbox with timeout."""
    safe_cmd = shlex.quote(command)
    sandbox_cmd = f"nohup sh -c {safe_cmd} < /dev/null > {output_file}  2>&1 &"

    response = await sandbox.arun(sandbox_cmd, session=session_name)
    pid = _extract_pid(response.output)
    if not pid:
        logger.error(f"Failed to extract PID from command output: {response.output}")
        return "execute error"
    while timeout_sec > 0:
        response = await sandbox.run_in_session(Action(command=f"kill -0 {pid}", session=session_name, check="silent"))
        if response.exit_code != 0:
            break
        await asyncio.sleep(1)
        timeout_sec -= 1
    if timeout_sec == 0:
        return "timeout"
    response = await sandbox.arun(f"cat {output_file}", session=session_name)
    return response.output


async def run_swe_evaluation(
    sandbox: Sandbox, task_dir: Path, task_name: str, question: str, config_path: str
) -> tuple[bool, dict[str, UnitTestStatus] | None]:
    """Run SWE evaluation on the sandbox."""
    # 1. Install agent
    await sandbox.agent.install(config=config_path)

    # 2. Prepare prompt
    prompt = SWE_PROMPT_TEMPLATE.format(workdir=sandbox.agent.config.project_path, question=question)
    result = await sandbox.agent.run(prompt)
    logger.info(f"Task name: {task_name}, sandbox id : {sandbox.sandbox_id}, Agent run result: {result}")

    # # 3. Install uv
    uv_install_script_commands = [
        "wget http://xrl-sandbox-bucket.oss-cn-hangzhou.aliyuncs.com/uv-files/uv-x86_64-unknown-linux-gnu.tar.gz",
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

    # 4. Setup test environment
    test_dir = task_dir / "tests"
    is_success = await _setup_test_env(sandbox, test_dir, task_dir / "run-tests.sh")
    if not is_success:
        logger.error("Failed to setup test environment")
        return False, None

    # 5. Run tests
    logger.info(f"Task name: {task_name}, sandbox id : {sandbox.sandbox_id}, Start to run tests")
    test_dir_path = "/tests"
    resp = await run_command_with_timeout(
        sandbox,
        f"bash {test_dir_path}/run-tests.sh",
        session_name,
        global_test_timeout_sec,
        f"{test_dir_path}/test.txt",
    )
    logger.info(f"Task name: {task_name}, sandbox id : {sandbox.sandbox_id}, Run tests result: {resp}")
    if resp == "timeout":
        return False, None
    elif resp == "execute error":
        logger.error(f"Failed to execute test command for task {task_name}")
        return False, None

    # 6. Parse results
    parserd_result = test_result_parser.parse(resp)
    resolve_result = is_resolved(parserd_result)
    logger.info(
        f"Task name: {task_name}, sandbox id : {sandbox.sandbox_id}, Parsed test result: {parserd_result}, is_resolved: {resolve_result}"
    )
    return resolve_result, parserd_result


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
                resolve_result, parse_result = await run_swe_evaluation(
                    sandbox, task_dir, task_name, question, config_path
                )
                logger.info(f"Completed evaluation for task: {task_name}")
                return {
                    "task_name": task_name,
                    "sandbox_id": sandbox.sandbox_id,
                    "status": "success",
                    "resolved": resolve_result,
                    "results": str(parse_result),
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
