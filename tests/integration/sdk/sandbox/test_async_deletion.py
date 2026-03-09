import pytest

from rock.actions.sandbox.response import State
from tests.integration.conftest import SKIP_IF_NO_DOCKER


@pytest.mark.need_admin
@SKIP_IF_NO_DOCKER
@pytest.mark.asyncio
async def test_async_container_deletion_feature(sandbox_instance):
    """Test that stopping a container makes it STOPPED instead of immediately deleted."""
    # Verify it's running
    status_before_stop = await sandbox_instance.get_status()
    assert status_before_stop.state == State.RUNNING
    assert status_before_stop.is_alive is True

    # Get original sandbox ID
    sandbox_id = sandbox_instance.sandbox_id
    assert sandbox_id is not None

    # Stop the sandbox
    await sandbox_instance.stop()

    # After stop, get status and verify it's in STOPPED state
    status_after_stop = await sandbox_instance.get_status()
    assert status_after_stop.state == State.STOPPED
    assert status_after_stop.sandbox_id == sandbox_id
    assert status_after_stop.is_alive is False


@pytest.mark.need_admin
@SKIP_IF_NO_DOCKER
@pytest.mark.asyncio
async def test_sandbox_stopped_state_persistence(sandbox_instance):
    """Test that stopped sandbox info is persisted in STOPPED state."""
    # Get original sandbox ID
    sandbox_id = sandbox_instance.sandbox_id
    assert sandbox_id is not None

    # Verify running state first
    status_running = await sandbox_instance.get_status()
    assert status_running.state == State.RUNNING
    assert status_running.sandbox_id == sandbox_id

    # Stop the sandbox
    await sandbox_instance.stop()

    # Verify it is still queryable and in STOPPED state
    status_stopped = await sandbox_instance.get_status()
    assert status_stopped.state == State.STOPPED
    assert status_stopped.sandbox_id == sandbox_id
    assert status_stopped.is_alive is False
