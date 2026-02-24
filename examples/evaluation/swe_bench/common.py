import re
from pathlib import Path

from rock.sdk.sandbox.client import RunMode, Sandbox
from rock.sdk.sandbox.config import SandboxConfig


async def load_task_config(task_dir: Path) -> dict:
    """Load task configuration from task.yaml."""
    import yaml

    task_yaml_path = task_dir / "task.yaml"
    if not task_yaml_path.exists():
        raise FileNotFoundError(f"task.yaml not found in {task_dir}")

    with open(task_yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


async def _install_uv(sandbox: Sandbox, session: str):
    uv_install_script_commands = [
        "wget https://github.com/astral-sh/uv/releases/download/0.10.5/uv-x86_64-unknown-linux-gnu.tar.gz",
        "tar -xzf uv-x86_64-unknown-linux-gnu.tar.gz --strip-components=1 -C /usr/local/bin",
    ]
    for uv_install_script in uv_install_script_commands:
        await sandbox.arun(uv_install_script, session=session, mode=RunMode.NOHUP)


async def setup_test_env(
    sandbox: Sandbox, test_folder: Path, test_dir: str, run_tests_scripts: Path, session: str
) -> bool:
    await _install_uv(sandbox, session)

    res = await sandbox.fs.upload_dir(test_folder, test_dir)
    if res.exit_code != 0:
        return False

    res = await sandbox.upload_by_path(run_tests_scripts, f"{test_dir}/{run_tests_scripts.name}")
    if not res.success:
        return False

    return True


def parse_swebench_result(output: str) -> bool:
    """Parse SWEBench test output to determine if the task is resolved.

    Matches the block between 'SWEBench results starts here' and
    'SWEBench results ends here', then checks whether it contains 'PASSED'.
    """
    match = re.search(
        r"SWEBench results starts here\s*(.*?)\s*SWEBench results ends here",
        output,
        re.DOTALL,
    )
    if not match:
        return False
    return match.group(1).strip() == "PASSED"


async def start_sandbox(swe_task_name: str) -> Sandbox:
    """Start a sandbox instance for evaluation."""
    image = f"slimshetty/swebench-verified:sweb.eval.x86_64.{swe_task_name}"
    config = SandboxConfig(image=image)
    sandbox = Sandbox(config)
    await sandbox.start()
    return sandbox
