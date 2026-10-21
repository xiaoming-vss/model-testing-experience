"""Worker entrypoint."""

from __future__ import annotations

import os
import signal
from pathlib import Path
from types import FrameType

from testing_agent_ai_worker_pi.app.bootstrap import (
    build_task_poller,
    build_task_runner,
    run_poll_once,
    run_worker,
)
from testing_agent_ai_worker_pi.config.loader import load_settings
from testing_agent_ai_worker_pi.logging.setup import setup_logging
from testing_agent_ai_worker_pi.pi_runtime.client import check_runtime, terminate_children
from testing_agent_ai_worker_pi.pi_runtime.config_builder import cleanup_task_configs

__all__ = [
    "build_task_poller",
    "build_task_runner",
    "main",
    "run_poll_once",
    "run_worker",
]


def main(config_path: str | Path | None = None) -> int:
    """CLI 入口。"""

    settings = load_settings(config_path)
    check_runtime(settings.pi.executable)

    def stop(signum: int, _frame: FrameType | None) -> None:
        terminate_children()
        cleanup_task_configs()
        os._exit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    setup_logging(settings.logging)
    return run_worker(settings=settings)
