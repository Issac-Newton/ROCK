import os
import shutil
from pathlib import Path


def compress_directory(local_dir, archive_name):
    """压缩本地目录为 .tar.gz"""
    base_name = archive_name.replace(".tar.gz", "")
    shutil.make_archive(base_name, "gztar", local_dir)


def cleanup_local(archive_name: str):
    """删除本地压缩文件"""
    if os.path.exists(archive_name):
        os.remove(archive_name)


async def load_task_config(task_dir: Path) -> dict:
    """Load task configuration from task.yaml."""
    import yaml

    task_yaml_path = task_dir / "task.yaml"
    if not task_yaml_path.exists():
        raise FileNotFoundError(f"task.yaml not found in {task_dir}")

    with open(task_yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config
