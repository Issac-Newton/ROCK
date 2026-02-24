from pathlib import Path


async def load_task_config(task_dir: Path) -> dict:
    """Load task configuration from task.yaml."""
    import yaml

    task_yaml_path = task_dir / "task.yaml"
    if not task_yaml_path.exists():
        raise FileNotFoundError(f"task.yaml not found in {task_dir}")

    with open(task_yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config
