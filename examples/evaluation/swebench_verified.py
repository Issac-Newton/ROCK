import sys

from rock.logger import init_logger
from rock.sdk.sandbox.client import Sandbox
from rock.sdk.sandbox.config import SandboxConfig

logger = init_logger(__name__)


async def start_sandbox(swe_task_name: str) -> Sandbox:
    """Start a sandbox instance for evaluation."""
    image = f"rock-registry.cn-hangzhou.cr.aliyuncs.com/slimshetty/swebench-verified:{swe_task_name}"
    config = SandboxConfig(image=image)
    sandbox = Sandbox(config)
    await sandbox.start()
    return sandbox


async def install_iflow_agent(sandbox: Sandbox, config_path: str) -> None:
    """Install iflow agent in sandbox."""
    await sandbox.agent.install(config=config_path)
    await sandbox.agent.runtime_env.run("iflow -v")
    logger.info("iflow agent installed successfully.")


if __name__ == "__main__":
    swe_task_dir = sys.argv[1]
    print(f"Starting sandbox for SWE evaluation with task: {swe_task_dir}")
    if not swe_task_dir:
        print("Error: SWE task name must be provided as a command-line argument.")
        sys.exit(1)

    parallel_num = sys.argv[2] if len(sys.argv) > 2 else "1"
    print(f"Using parallel_num: {parallel_num}")
