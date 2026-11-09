"""Worker entrypoint."""

from __future__ import annotations

import os
import signal
from pathlib import Path
from types import FrameType

from testing_agent_ai_worker.agent import (
    cleanup_task_configs,
    terminate_children,
    verify_runtime,
)
from testing_agent_ai_worker.app.bootstrap import (
    build_task_poller,
    build_task_runner,
    run_poll_once,
    run_worker,
)
from testing_agent_ai_worker.app.health import HealthServer, health_port_from_env
from testing_agent_ai_worker.config.loader import load_settings
from testing_agent_ai_worker.logging.setup import setup_logging

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
    verify_runtime(settings.agent.active)
    stopping = False

    def stop(signum: int, _frame: FrameType | None) -> None:
        nonlocal stopping
        # 重复 SIGTERM 不重入清理逻辑，避免在信号上下文里执行未完成的导入。
        if stopping:
            return
        stopping = True
        terminate_children()
        cleanup_task_configs()
        os._exit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    setup_logging(settings.logging)
    # 本地开发不注入探针端口，此时不启动 health server。
    health_port = health_port_from_env()
    health_server = HealthServer(port=health_port) if health_port is not None else None
    if health_server is not None:
        health_server.start()
    try:
        return run_worker(settings=settings)
    finally:
        if health_server is not None:
            health_server.stop()
