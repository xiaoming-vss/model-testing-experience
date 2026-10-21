"""Create private invocation configuration using control-plane credentials."""

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from testing_agent_ai_worker_pi.config.models import PiConfig
from testing_agent_ai_worker_pi.models.task import Task
from testing_agent_ai_worker_pi.pi_runtime.paths import resolve_runtime_paths

_CONFIGS: set[Path] = set()
_CONFIG_LOCK = threading.Lock()


def cleanup_task_configs() -> None:
    """Remove active credential files before immediate Worker shutdown."""
    with _CONFIG_LOCK:
        for path in tuple(_CONFIGS):
            path.unlink(missing_ok=True)
        _CONFIGS.clear()


@contextmanager
def task_config_path(*, pi_config: PiConfig, task: Task) -> Iterator[str]:
    credentials = task.payload.llm_credentials
    runtime = resolve_runtime_paths(pi_config)
    runtime.temp_configs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        **pi_config.model_dump(),
        "runtime_root": str(runtime.runtime_root.resolve()),
        "model": credentials.model if credentials else "",
        "base_url": credentials.base_url if credentials else "",
        "api_key": credentials.api_key if credentials else "",
    }
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="pi-task-",
        dir=runtime.temp_configs_dir,
        delete=False,
    ) as stream:
        json.dump(payload, stream)
        path = Path(stream.name)
        with _CONFIG_LOCK:
            _CONFIGS.add(path)
    try:
        yield str(path)
    finally:
        with _CONFIG_LOCK:
            _CONFIGS.discard(path)
            path.unlink(missing_ok=True)
