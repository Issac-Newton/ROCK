ALIVE_PREFIX = "alive:"
TIMEOUT_PREFIX = "timeout:"
STOPPED_PREFIX = "stopped:"


def alive_sandbox_key(sandbox_id: str) -> str:
    return f"{ALIVE_PREFIX}{sandbox_id}"


def timeout_sandbox_key(sandbox_id: str) -> str:
    return f"{TIMEOUT_PREFIX}{sandbox_id}"


def stopped_sandbox_key(sandbox_id: str) -> str:
    return f"{STOPPED_PREFIX}{sandbox_id}"
