"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from .app import run_once
from .contracts.result import RunResult, RunStatus
from .core.config import Settings, load_settings
from .core.errors import PerfWorkerError
from .core.logging import configure_logging
from .worker.health import HealthFile
from .worker.poller import PerfPoller

_HEALTH_PROGRESS_INTERVAL_SECONDS = 30


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mtx-perf-worker")
    parser.add_argument("--config", help="配置文件路径；缺省使用 APP_CONF 或 config/local.toml")
    parser.add_argument("--healthcheck", action="store_true", help="检查健康文件并退出")
    args = parser.parse_args(argv)

    if args.healthcheck:
        return _healthcheck(args.config)

    configure_logging()
    logger = logging.getLogger("testing_agent_perf_worker")
    health: HealthFile | None = None
    try:
        settings = load_settings(args.config)
        health = HealthFile(
            Path(settings.worker.health_file),
            settings.worker.health_max_age_seconds,
        )
        if settings.mode == "poll":
            health.progress("starting")
            asyncio.run(PerfPoller(settings).run())
            return 0
        if not settings.once.snapshot_file:
            raise PerfWorkerError("once 模式缺少 [once].snapshot_file")

        health.progress("starting")
        result = asyncio.run(_run_with_health(settings, Path(settings.once.snapshot_file), health))
        health.progress("finished")
        print(result.model_dump_json(by_alias=True, indent=2))
        if result.status in {RunStatus.COMPLETED, RunStatus.STOPPED}:
            return 0
        return 1
    except PerfWorkerError as exc:
        _mark_failed(health)
        logger.error("perf worker failed: %s", exc)
        return 1
    except KeyboardInterrupt:
        _mark_failed(health)
        logger.warning("perf worker interrupted")
        return 130
    except Exception:
        _mark_failed(health)
        logger.exception("perf worker unexpected error")
        return 1


async def _run_with_health(settings: Settings, spec_path: Path, health: HealthFile) -> RunResult:
    task = asyncio.create_task(run_once(settings, spec_path))
    while not task.done():
        health.progress("running")
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=_HEALTH_PROGRESS_INTERVAL_SECONDS,
            )
        except TimeoutError:
            continue
    return task.result()


def _healthcheck(config_path: str | None) -> int:
    try:
        settings = load_settings(config_path)
    except PerfWorkerError:
        return 1
    health = HealthFile(
        Path(settings.worker.health_file),
        settings.worker.health_max_age_seconds,
    )
    return 0 if health.healthy() else 1


def _mark_failed(health: HealthFile | None) -> None:
    if health is None:
        return
    try:
        health.progress("failed")
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
