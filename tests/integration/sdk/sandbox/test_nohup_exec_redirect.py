"""
Reproduce the issue where arun nohup mode loses tail output of run-tests.sh.

Uses the real swebench run-tests.sh script and the same sandbox image to reproduce.
Compares two approaches:
  1. SDK arun(mode="nohup") — the buggy path
  2. Manual nohup sh -c wrapper (from swebench_verified.py) — the working path
"""

import asyncio
import re
import shlex
from pathlib import Path

import pytest

from rock.actions import Action
from rock.actions.sandbox.request import CreateBashSessionRequest
from rock.sdk.sandbox.client import RunMode, Sandbox
from tests.integration.conftest import SKIP_IF_NO_DOCKER

# Marker text printed by parser.py at the end of run-tests.sh
EXPECTED_TAIL_MARKER = "SWEBench results starts here"

# Use a known swebench task for reproducibility
SWE_TASK_NAME = "django__django-10554"

# swebench docker image
SWE_IMAGE = f"rock-registry.cn-hangzhou.cr.aliyuncs.com/slimshetty/swebench-verified:sweb.eval.x86_64.{SWE_TASK_NAME}"

# Timeouts
TEST_TIMEOUT_SEC = 600


def _extract_pid(output: str) -> str:
    """Extract PID from nohup background job output (e.g. '[1] 12345')."""
    for line in reversed(output.splitlines()):
        match = re.match(r"\[\d+\]\s+(\d+)", line.strip())
        if match:
            return match.group(1)
    return ""


async def _run_command_with_timeout(
    sandbox: Sandbox, command: str, session_name: str, timeout_sec: int, output_file: str
) -> str:
    """
    Run a command using manual nohup with sh -c wrapper.
    Copied from examples/evaluation/swebench_verified.py — the working approach.
    """
    safe_cmd = shlex.quote(command)
    sandbox_cmd = f"nohup sh -c {safe_cmd} < /dev/null > {output_file}  2>&1 &"

    response = await sandbox.arun(sandbox_cmd, session=session_name)
    pid = _extract_pid(response.output)
    if not pid:
        return f"execute error: could not extract PID from: {response.output}"

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


async def _setup_test_env(sandbox: Sandbox, session_name: str) -> bool:
    """Upload run-tests.sh and test config, install uv — mirrors swebench_verified.py."""
    task_dir = Path(__file__).parent.parent.parent.parent.parent / "swebench-verified" / SWE_TASK_NAME
    tests_dir = task_dir / "tests"
    run_tests_script = task_dir / "run-tests.sh"

    if not run_tests_script.exists():
        pytest.skip(f"run-tests.sh not found at {run_tests_script}")

    test_remote_dir = "/tests"
    res = await sandbox.fs.upload_dir(tests_dir, test_remote_dir)
    if res.exit_code != 0:
        return False

    res = await sandbox.upload_by_path(run_tests_script, f"{test_remote_dir}/run-tests.sh")
    if not res.success:
        return False

    # Install uv (same as swebench_verified.py)
    uv_install_commands = [
        "wget http://xrl-sandbox-bucket.oss-cn-hangzhou.aliyuncs.com/uv-files/uv-x86_64-unknown-linux-gnu.tar.gz",
        "tar -xzf uv-x86_64-unknown-linux-gnu.tar.gz --strip-components=1 -C /usr/local/bin",
    ]
    for cmd in uv_install_commands:
        result = await sandbox.arun(cmd, session=session_name, mode=RunMode.NOHUP, wait_timeout=300)
        if result.exit_code != 0:
            return False

    return True


@pytest.mark.parametrize(
    "sandbox_instance",
    [{"image": SWE_IMAGE}],
    indirect=True,
)
@pytest.mark.need_admin
@SKIP_IF_NO_DOCKER
@pytest.mark.asyncio
async def test_nohup_output_loss_with_real_run_tests_sh(sandbox_instance: Sandbox):
    """
    Reproduce the output loss bug using the real swebench run-tests.sh script.

    Runs the same script with two different nohup approaches:
      1. SDK arun(mode="nohup") — expected to lose tail output
      2. Manual nohup sh -c wrapper — expected to preserve tail output
    """
    session_name = "swe-evaluation"
    await sandbox_instance.create_session(
        CreateBashSessionRequest(
            session=session_name,
            env_enable=True,
            env={"UV_PYTHON_INSTALL_MIRROR": "https://registry.npmmirror.com/-/binary/python-build-standalone"},
        )
    )

    is_success = await _setup_test_env(sandbox_instance, session_name)
    assert is_success, "Failed to setup test environment"

    test_script_path = "/tests/run-tests.sh"

    # --- Method 1: SDK arun nohup mode (the buggy path) ---
    print("\n=== Running with SDK arun nohup mode ===")
    sdk_result = await sandbox_instance.arun(
        cmd=f"bash {test_script_path}",
        session=session_name,
        mode="nohup",
        wait_timeout=TEST_TIMEOUT_SEC,
    )
    sdk_output = sdk_result.output
    sdk_has_marker = EXPECTED_TAIL_MARKER in sdk_output
    # assert sdk_has_marker

    sdk_tail_lines = sdk_output.splitlines()[-20:]
    print(f"SDK output length: {len(sdk_output)}")
    print(f"SDK has tail marker: {sdk_has_marker}")
    print("SDK last 20 lines:\n" + "\n".join(sdk_tail_lines))

    # --- Method 2: Manual nohup sh -c wrapper (the working path) ---
    print("\n=== Running with manual nohup sh -c wrapper ===")
    manual_output = await _run_command_with_timeout(
        sandbox=sandbox_instance,
        command=f"bash {test_script_path}",
        session_name=session_name,
        timeout_sec=TEST_TIMEOUT_SEC,
        output_file="/tests/test_manual.txt",
    )
    manual_has_marker = EXPECTED_TAIL_MARKER in manual_output

    manual_tail_lines = manual_output.splitlines()[-20:]
    print(f"Manual output length: {len(manual_output)}")
    print(f"Manual has tail marker: {manual_has_marker}")
    print("Manual last 20 lines:\n" + "\n".join(manual_tail_lines))

    # --- Assertions ---
    print("\n=== Summary ===")
    print(f"  SDK arun nohup: has_marker={sdk_has_marker}, output_len={len(sdk_output)}")
    print(f"  Manual sh -c:   has_marker={manual_has_marker}, output_len={len(manual_output)}")

    # Manual approach must work
    assert manual_has_marker, "Manual nohup sh -c should capture tail output, but got last lines:\n" + "\n".join(
        manual_tail_lines
    )

    # SDK approach should fail (reproducing the bug)
    assert not sdk_has_marker, (
        "Expected SDK arun nohup to LOSE tail output (reproducing the bug), "
        "but it was found. The bug may have been fixed.\n"
        "SDK last lines:\n" + "\n".join(sdk_tail_lines)
    )

    print("\n✅ Bug reproduced: SDK arun nohup loses tail output, manual sh -c preserves it.")
