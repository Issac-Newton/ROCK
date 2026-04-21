import os

import pytest

from rock import env_vars
from rock.actions import (
    BashAction,
    CloseBashSessionRequest,
    Command,
    CreateBashSessionRequest,
)
from rock.deployments.config import DockerDeploymentConfig, get_deployment


@pytest.mark.need_docker
async def test_docker_deployment(container_name):
    deployment_config = DockerDeploymentConfig(
        image=env_vars.ROCK_ENVHUB_DEFAULT_DOCKER_IMAGE,
        container_name=container_name,
    )
    d = get_deployment(deployment_config)
    with pytest.raises(RuntimeError):
        await d.is_alive()
    await d.start()
    assert await d.is_alive()
    command = Command(command=["echo", "hello"])
    await d.runtime.execute(command)

    # test bash session with default env
    create_session_request = CreateBashSessionRequest(session_type="bash")
    await d.runtime.create_session(create_session_request)
    action = BashAction(command="echo $PATH")
    path_result_with_env = await d.runtime.run_in_session(action)
    print(path_result_with_env.output)
    action = BashAction(command="echo $HOME")
    home_result_with_env = await d.runtime.run_in_session(action)
    print(home_result_with_env.output)
    close_session_request = CloseBashSessionRequest(session_type="bash")
    await d.runtime.close_session(close_session_request)

    # test bash session without default env
    create_session_request = CreateBashSessionRequest(session_type="bash", env_enable=False)
    await d.runtime.create_session(create_session_request)
    action = BashAction(command="echo $PATH")
    path_result = await d.runtime.run_in_session(action)
    print(path_result.output)
    action = BashAction(command="echo $HOME")
    home_result = await d.runtime.run_in_session(action)
    print(home_result.output)
    close_session_request = CloseBashSessionRequest(session_type="bash")
    await d.runtime.close_session(close_session_request)
    await d.stop()


@pytest.mark.need_docker
async def test_docker_deployment_passes_tz_env_to_container(container_name):
    original_tz = os.environ.get("TZ")
    os.environ["TZ"] = "EST5EDT"
    try:
        env_vars.__dict__.pop("TZ", None)

        deployment_config = DockerDeploymentConfig(
            image=env_vars.ROCK_ENVHUB_DEFAULT_DOCKER_IMAGE,
            container_name=container_name,
        )
        d = get_deployment(deployment_config)
        try:
            await d.start()
            assert await d.is_alive()

            command = Command(command=["/bin/sh", "-lc", 'printf %s "$TZ"'])
            tz_result = await d.runtime.execute(command)

            assert tz_result.stdout.strip() == "EST5EDT"
        finally:
            await d.stop()
    finally:
        env_vars.__dict__.pop("TZ", None)
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz


@pytest.mark.need_docker
async def test_docker_deployment_tz_defaults_to_cst8_when_unset(container_name):
    original_tz = os.environ.pop("TZ", None)
    try:
        env_vars.__dict__.pop("TZ", None)

        deployment_config = DockerDeploymentConfig(
            image=env_vars.ROCK_ENVHUB_DEFAULT_DOCKER_IMAGE,
            container_name=container_name,
        )
        d = get_deployment(deployment_config)
        try:
            await d.start()
            assert await d.is_alive()

            command = Command(command=["/bin/sh", "-lc", 'printf %s "$TZ"'])
            tz_result = await d.runtime.execute(command)

            assert tz_result.stdout.strip() == "CST-8"
        finally:
            await d.stop()
    finally:
        env_vars.__dict__.pop("TZ", None)
        if original_tz is not None:
            os.environ["TZ"] = original_tz


def test_docker_deployment_config_platform():
    config = DockerDeploymentConfig(docker_args=["--platform", "linux/amd64", "--other-arg"])
    assert config.platform == "linux/amd64"

    config = DockerDeploymentConfig(docker_args=["--platform=linux/amd64", "--other-arg"])
    assert config.platform == "linux/amd64"

    config = DockerDeploymentConfig(docker_args=["--other-arg"])
    assert config.platform is None

    with pytest.raises(ValueError):
        config = DockerDeploymentConfig(platform="linux/amd64", docker_args=["--platform", "linux/amd64"])
    with pytest.raises(ValueError):
        config = DockerDeploymentConfig(platform="linux/amd64", docker_args=["--platform=linux/amd64"])
