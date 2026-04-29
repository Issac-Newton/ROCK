"""Integration tests for Image.from_dockerfile() → Sandbox.start() flow.

Verifies that a sandbox can be started from a local Dockerfile directory,
including build, cache skip, and content-change rebuild scenarios.

Run: pytest tests/integration/sdk/sandbox/test_image_build.py -v -m need_admin
"""

import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from rock.actions.sandbox.request import CreateBashSessionRequest
from rock.logger import init_logger
from rock.sdk.sandbox.client import Sandbox
from rock.sdk.sandbox.config import SandboxConfig
from rock.sdk.sandbox.image import Image

logger = init_logger(__name__)

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "test_data" / "image_from_dockerfile"
EXPECTED_FILE_CONTENT = "rock-image-from-dockerfile-ok"
MODIFIED_CONTENT = "rock-content-changed"


# ── Helpers ──


def _create_image(env_dir, registry_info, **kwargs):
    return Image.from_dockerfile(
        env_dir,
        image_name=registry_info["image_tag"],
        registry_username=registry_info["registry_username"],
        registry_password=registry_info["registry_password"],
        **kwargs,
    )


def _create_config(image, admin_remote_server):
    base_url = f"{admin_remote_server.endpoint}:{admin_remote_server.port}"
    return SandboxConfig(image=image, memory="2g", cpus=1.0, startup_timeout=600, base_url=base_url)


@asynccontextmanager
async def _run_sandbox(config):
    """Start a sandbox with default session, yield it, always stop on exit."""
    sandbox = Sandbox(config)
    try:
        await sandbox.start()
        await sandbox.create_session(CreateBashSessionRequest(session="default"))
        yield sandbox
    finally:
        try:
            await sandbox.stop()
        except Exception as e:
            logger.warning("Failed to stop sandbox: %s", e)


async def _assert_file_content(sandbox, expected):
    result = await sandbox.arun(cmd="cat /opt/hello.txt", session="default")
    assert result.output is not None
    assert result.output.strip() == expected


# ── Fixtures ──


@pytest.fixture
def local_registry_info(local_registry):
    registry_url, username, password = local_registry
    return {
        "image_tag": f"{registry_url}/rock-test/image-from-dockerfile:latest",
        "registry_username": username,
        "registry_password": password,
    }


@pytest.fixture
def modified_env_dir(tmp_path):
    """Copy test data and modify hello.txt to detect rebuild."""
    env_dir = tmp_path / "env"
    shutil.copytree(TEST_DATA_DIR, env_dir)
    (env_dir / "hello.txt").write_text(MODIFIED_CONTENT + "\n")
    return env_dir


# ── Tests ──


@pytest.mark.need_admin
@pytest.mark.asyncio
async def test_from_dockerfile_build_and_start(local_registry_info, admin_remote_server):
    """Image.from_dockerfile() → Sandbox.start() → verify COPY file accessible."""
    image = _create_image(TEST_DATA_DIR, local_registry_info)
    config = _create_config(image, admin_remote_server)
    async with _run_sandbox(config) as sandbox:
        await _assert_file_content(sandbox, EXPECTED_FILE_CONTENT)


@pytest.mark.need_admin
@pytest.mark.asyncio
async def test_from_dockerfile_cache_skip(local_registry_info, admin_remote_server):
    """Second start with same Image should skip build (cache hit)."""
    image = _create_image(TEST_DATA_DIR, local_registry_info)
    config = _create_config(image, admin_remote_server)

    async with _run_sandbox(config):
        first_duration = time.monotonic()
    first_duration = time.monotonic() - first_duration

    t0 = time.monotonic()
    async with _run_sandbox(config) as sandbox:
        second_duration = time.monotonic() - t0
        await _assert_file_content(sandbox, EXPECTED_FILE_CONTENT)

    logger.info("First build: %.1fs, second build: %.1fs", first_duration, second_duration)
    assert second_duration < first_duration


@pytest.mark.need_admin
@pytest.mark.asyncio
async def test_from_dockerfile_rebuilds_on_content_change(local_registry_info, admin_remote_server, modified_env_dir):
    """Content change in env_dir triggers rebuild, new file content is picked up."""
    image = _create_image(modified_env_dir, local_registry_info)
    config = _create_config(image, admin_remote_server)
    async with _run_sandbox(config) as sandbox:
        await _assert_file_content(sandbox, MODIFIED_CONTENT)
