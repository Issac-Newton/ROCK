import os
import shutil
from pathlib import Path

import pytest

from rock.logger import init_logger
from rock.sdk.sandbox.client import Sandbox
from tests.integration.conftest import SKIP_IF_NO_DOCKER

logger = init_logger(__name__)

SWE_PROMPT_TEMPLATE = """
 <uploaded_files>
  {workdir}
  </uploaded_files>

  I've uploaded a python code repository in the directory /testbed. Consider the following issue description:

  <issue_description>
  {question}
  </issue_description>

  Can you help me implement the necessary changes to the repository so that the requirements specified in the <issue_description> are met?
  I've already taken care of all changes to any of the test files described in the <issue_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!
  Also the development Python environment is already set up for you (i.e., all dependencies already installed), so you don't need to install other packages.
  Your task is to make the minimal changes to non-test files in the /testbed directory to ensure the <issue_description> is satisfied.

  Follow these phases to resolve the issue:

  Phase 1. READING: read the problem and reword it in clearer terms
    1.1 If there are code or config snippets. Express in words any best practices or conventions in them.
    1.2 Highlight message errors, method names, variables, file names, stack traces, and technical details.
    1.3 Explain the problem in clear terms.
    1.4 Enumerate the steps to reproduce the problem.
    1.5 Highlight any best practices to take into account when testing and fixing the issue

  Phase 2. RUNNING: install and run the tests on the repository
    2.1 Follow the readme
    2.2 Install the environment and anything needed
    2.3 Iterate and figure out how to run the tests

  Phase 3. EXPLORATION: find the files that are related to the problem and possible solutions
    3.1 Use `grep` to search for relevant methods, classes, keywords and error messages.
    3.2 Identify all files related to the problem statement.
    3.3 Propose the methods and files to fix the issue and explain why.
    3.4 From the possible file locations, select the most likely location to fix the issue.

  Phase 4. TEST CREATION: before implementing any fix, create a script to reproduce and verify the issue.
    4.1 Look at existing test files in the repository to understand the test format/structure.
    4.2 Create a minimal reproduction script that reproduces the located issue.
    4.3 Run the reproduction script to confirm you are reproducing the issue.
    4.4 Adjust the reproduction script as necessary.

  Phase 5. FIX ANALYSIS: state clearly the problem and how to fix it
    5.1 State clearly what the problem is.
    5.2 State clearly where the problem is located.
    5.3 State clearly how the test reproduces the issue.
    5.4 State clearly the best practices to take into account in the fix.
    5.5 State clearly how to fix the problem.

  Phase 6. FIX IMPLEMENTATION: Edit the source code to implement your chosen solution.
    6.1 Make minimal, focused changes to fix the issue.

  Phase 7. VERIFICATION: Test your implementation thoroughly.
    7.1 Run your reproduction script to verify the fix works.
    7.2 Add edge cases to your test script to ensure comprehensive coverage.
    7.3 Run existing tests related to the modified code to ensure you haven't broken anything.

  8. FINAL REVIEW: Carefully re-read the problem description and compare your changes with the base commit.
    8.1 Ensure you've fully addressed all requirements.
    8.2 Run any tests in the repository related to:
      8.2.1 The issue you are fixing
      8.2.2 The files you modified
      8.2.3 The functions you changed
    8.3 If any tests fail, revise your implementation until all tests pass

  Be thorough in your exploration, testing, and reasoning. It's fine if your thinking process is lengthy - quality and completeness are more important than brevity.
"""


def compress_directory(local_dir, archive_name):
    """压缩本地目录为 .tar.gz"""
    # print(f"📦 正在压缩 {local_dir} -> {archive_name}")
    # 使用 gztar 格式压缩
    base_name = archive_name.replace(".tar.gz", "")
    shutil.make_archive(base_name, "gztar", local_dir)
    # print(f"✅ 压缩完成: {archive_name}")


def cleanup_local(archive_name: str):
    """删除本地压缩文件"""
    if os.path.exists(archive_name):
        os.remove(archive_name)
        # print(f"🗑️ 已删除本地压缩包: {archive_name}")
    # else:
    #     print(f"⚠️ 本地压缩包不存在，跳过删除: {archive_name}")


# def _setup_test_env_compress(
#         self, sb: BaseSandbox, test_session_name, trial_handler: TrialHandler
#     ) -> bool:
#     test_dir = "/tests"
#     response = sb.run_command(f"mkdir -p  {test_dir}", test_session_name, True)
#     if response.exit_code != 0:
#         self._logger.error(f"Failed to create test directory: {response}")
#         return False
#     path = trial_handler.task_paths.run_tests_path

#     response = sb.upload_file(path, f"{test_dir}/{path.name}")
#     if not response.is_success:
#         self._logger.error(
#             f"Sandbox upload failed: path={path}, target={test_dir}/{path.name}"
#         )
#         return False
#     if trial_handler.task_paths.test_dir.exists():
#         temp = "temp.tar.gz"
#         compress_directory(
#             trial_handler.task_paths.test_dir,
#             f"{trial_handler.task_paths.test_dir.as_posix()}/{temp}",
#         )
#         response = sb.upload_file(
#             f"{trial_handler.task_paths.test_dir.as_posix()}/{temp}",
#             f"{test_dir}/{temp}",
#         )
#         if not response.is_success:
#             self._logger.error(
#                 f"Sandbox upload failed: path={path}, target={test_dir}/{temp}"
#             )
#             return False
#         response = sb.run_command(
#             f"tar -xzf {test_dir}/{temp}  -C {test_dir}", test_session_name, False
#         )
#         if response.exit_code != 0:
#             self._logger.error(f"Failed to extract test files: {response}")
#             return False
#         cleanup_local(trial_handler.task_paths.test_dir / temp)
#     return True


# def _run_tests(
#     self,
#     sb: BaseSandbox,
#     test_session_name: str,
#     trial_handler: TrialHandler,
#     ) -> tuple[str, str]:
#     is_success = self._setup_test_env_compress(sb, test_session_name, trial_handler)
#     if not is_success:
#         return "", "Setup test env failed"
#     # 5、进行评测
#     test_dir = "/tests"
#     resp = sb.run_command_with_timeout(
#         f"bash {test_dir}/{trial_handler.task_paths.run_tests_path.name}",
#         int(self._global_test_timeout_sec),
#         f"{test_dir}/test.txt",
#         test_session_name,
#         True,
#         trial_handler.trial_paths.test_log_path,
#     )
#     if resp.run_status != RunStatus.SUCCESS:
#         if resp.run_status == RunStatus.TIMEOUT:
#             return "", FailureMode.TEST_TIMEOUT
#     return resp.output, FailureMode.NONE


@pytest.mark.need_admin_and_network
@SKIP_IF_NO_DOCKER
@pytest.mark.asyncio
async def test_iflow_run_swe_evaluation(sandbox_instance: Sandbox, monkeypatch) -> None:
    config_path = "iflow_swe_config.yaml"
    test_dir = Path(__file__).resolve().parent
    monkeypatch.chdir(test_dir)

    await sandbox_instance.agent.install(config=config_path)

    # 1. 先把prompt模版抄过来
    question = "InheritDocstrings metaclass doesn't work for properties\nInside the InheritDocstrings metaclass it uses `inspect.isfunction` which returns `False` for properties.\n"
    prompt = SWE_PROMPT_TEMPLATE.format(workdir=sandbox_instance.agent.config.project_path, question=question)
    result = await sandbox_instance.agent.run(prompt)
    logger.info(result)
