import re
import shlex
from pathlib import Path

from rock.common.constants import PID_PREFIX, PID_SUFFIX
from rock.sdk.sandbox.client import Sandbox
from rock.utils.system import extract_nohup_pid


async def load_task_config(task_dir: Path) -> dict:
    """Load task configuration from task.yaml."""
    import yaml

    task_yaml_path = task_dir / "task.yaml"
    if not task_yaml_path.exists():
        raise FileNotFoundError(f"task.yaml not found in {task_dir}")

    with open(task_yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


async def setup_test_env(sandbox: Sandbox, test_folder: Path, test_dir: str, run_tests_scripts: Path) -> bool:
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


async def run_command_with_timeout(
    sandbox: Sandbox, command: str, session_name: str, timeout_sec: int, output_file: str
) -> str:
    """Run a command in sandbox with timeout."""
    safe_cmd = shlex.quote(command)
    sandbox_cmd = f"nohup sh -c {safe_cmd} < /dev/null > {output_file}  2>&1 & echo {PID_PREFIX}${{!}}{PID_SUFFIX}"

    response = await sandbox.arun(sandbox_cmd, session=session_name)
    pid = extract_nohup_pid(response.output)
    success, message = await sandbox.wait_for_process_completion(
        pid=pid, session=session_name, wait_timeout=timeout_sec, wait_interval=10
    )
    observation = await sandbox.handle_nohup_output(
        tmp_file=output_file,
        session=session_name,
        success=success,
        message=message,
        ignore_output=False,
        response_limited_bytes_in_nohup=None,
    )
    return observation.output
