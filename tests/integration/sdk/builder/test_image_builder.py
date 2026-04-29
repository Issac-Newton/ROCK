"""
Integration test for ImageBuilder: build a Docker image from env_dir inside a
builder sandbox and push to a local registry with auth.

Adapted from PR #534 (test_env_dir_build.py).

Run: pytest tests/integration/sdk/builder/test_image_builder.py -v
  (with admin available and docker on the worker node)
"""
import tempfile
from pathlib import Path

import pytest

from rock.actions.sandbox.request import CreateBashSessionRequest
from rock.logger import init_logger
from rock.sdk.builder.image_builder import ImageBuilder
from rock.sdk.sandbox.client import Sandbox
from rock.sdk.sandbox.config import SandboxConfig
from tests.integration.conftest import SKIP_IF_NO_DOCKER

logger = init_logger(__name__)

ENV_DIR_TEST_FILE_CONTENT = "rock-image-builder-ok"


@pytest.fixture
def minimal_env_dir():
    """A minimal docker build context: Dockerfile + a file to test COPY."""
    with tempfile.TemporaryDirectory(prefix="rock_env_dir_") as tmp:
        path = Path(tmp)
        (path / "app.txt").write_text(ENV_DIR_TEST_FILE_CONTENT)
        (path / "Dockerfile").write_text("FROM python:3.11\n" "COPY app.txt /opt/app.txt\n")
        yield path


@pytest.mark.need_admin
@SKIP_IF_NO_DOCKER
@pytest.mark.asyncio
async def test_image_builder_build_and_run_in_sandbox(admin_remote_server, local_registry, minimal_env_dir):
    """Build image via ImageBuilder, then start a new sandbox from the pushed
    image and verify the file content inside the sandbox (same pattern as
    PR #534 test_env_dir_build)."""
    registry_url, registry_user, registry_pass = local_registry
    image_tag = f"{registry_url}/rock-test/image-builder-sandbox-test:latest"
    base_url = f"{admin_remote_server.endpoint}:{admin_remote_server.port}"

    builder = ImageBuilder()
    await builder.build(
        instance_record={"env_dir": str(minimal_env_dir), "image_tag": image_tag},
        base_url=base_url,
        registry_username=registry_user,
        registry_password=registry_pass,
        memory="2g",
        cpus=1.0,
    )

    # Start a sandbox from the built image and verify
    config = SandboxConfig(
        image=image_tag,
        memory="2g",
        cpus=1.0,
        startup_timeout=300,
        base_url=base_url,
        registry_username=registry_user,
        registry_password=registry_pass,
    )
    sandbox = Sandbox(config)
    try:
        await sandbox.start()
        assert sandbox.sandbox_id
        await sandbox.create_session(CreateBashSessionRequest(session="default"))

        result = await sandbox.arun(cmd="echo ok", session="default")
        assert result.output is not None
        assert "ok" in result.output

        cat_result = await sandbox.arun(cmd="cat /opt/app.txt", session="default")
        assert cat_result.output is not None
        assert cat_result.output.strip() == ENV_DIR_TEST_FILE_CONTENT
    finally:
        try:
            await sandbox.stop()
        except Exception as e:
            logger.warning("Failed to stop sandbox: %s", e)
