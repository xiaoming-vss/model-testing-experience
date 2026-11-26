"""
主入口模块
支持 poll 和 once 两种模式
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
from pathlib import Path

from .core import logger
from .api.case_runner import ApiCaseRunner
from .api.collection_runner import ApiCollectionRunner
from .core.config import load_config
from .control_plane.client import ControlPlaneClient
from .health import HealthServer, health_port_from_env
from .contracts.parsing import (
    parse_case_run_snapshot,
    parse_snapshot_response,
    parse_suite_run_snapshot,
)
from .contracts.types import WorkerConfig
from .ui.case_runner import UiCaseRunner
from .ui.suite_runner import UiSuiteRunner


async def _run_once(
    snapshot_file: str,
    case_runner: UiCaseRunner,
    suite_runner: UiSuiteRunner,
) -> None:
    """
    执行 once 模式

    Args:
        snapshot_file: 快照文件路径
        case_runner: 用例运行器
        suite_runner: 测试集运行器

    Raises:
        ValueError: 快照文件为空或内容无效时抛出
    """
    if not snapshot_file:
        raise ValueError("once 模式缺少 config.toml 中的 [once].snapshot_file")

    # 读取快照文件
    content = Path(snapshot_file).resolve().read_text(encoding="utf-8")
    parsed = json.loads(content)

    # 解析快照
    if "taskType" in parsed:
        if parsed.get("taskType") == "api_case_debug" and parsed.get("caseRun"):
            api_case_result = await ApiCaseRunner().run(parsed["caseRun"])
            logger.info(
                "once mode api case result",
                {
                    "taskId": api_case_result.get("taskId"),
                    "status": api_case_result.get("status"),
                    "success": api_case_result.get("success"),
                },
            )
            return

        if parsed.get("taskType") == "api_collection_run" and parsed.get(
            "collectionRun"
        ):
            api_collection_result = await ApiCollectionRunner(
                _NoopControlPlaneClient()
            ).run(parsed["collectionRun"])
            logger.info(
                "once mode api collection result",
                {
                    "taskId": api_collection_result.get("taskId"),
                    "status": api_collection_result.get("status"),
                    "success": api_collection_result.get("success"),
                },
            )
            return

        snapshot = parse_snapshot_response(parsed)
        if snapshot.task_type == "suite_run" and snapshot.suite_run:
            suite_result = await suite_runner.run(snapshot.suite_run)
            logger.info(
                "once mode suite result",
                {
                    "taskId": suite_result.task_id,
                    "status": suite_result.status,
                    "success": suite_result.success,
                },
            )
            return

        if snapshot.task_type == "case_debug" and snapshot.case_run:
            case_result = await case_runner.run(snapshot.case_run)
            logger.info(
                "once mode case result",
                {
                    "taskId": case_result.task_id,
                    "status": case_result.status,
                    "success": case_result.success,
                },
            )
            return

        raise ValueError("once 模式快照缺少可执行内容")

    if "collectionRunId" in parsed and "items" in parsed:
        api_collection_result = await ApiCollectionRunner(
            _NoopControlPlaneClient()
        ).run(parsed)
        logger.info(
            "once mode api collection result",
            {
                "taskId": api_collection_result.get("taskId"),
                "status": api_collection_result.get("status"),
                "success": api_collection_result.get("success"),
            },
        )
        return

    # 直接是测试集快照
    if "items" in parsed:
        suite_snapshot = parse_suite_run_snapshot(parsed)
        if suite_snapshot is None:
            raise ValueError("once 模式测试集快照为空")
        suite_result = await suite_runner.run(suite_snapshot)
        logger.info(
            "once mode suite result",
            {
                "taskId": suite_result.task_id,
                "status": suite_result.status,
                "success": suite_result.success,
            },
        )
        return

    if "request" in parsed and "caseId" in parsed:
        api_case_result = await ApiCaseRunner().run(parsed)
        logger.info(
            "once mode api case result",
            {
                "taskId": api_case_result.get("taskId"),
                "status": api_case_result.get("status"),
                "success": api_case_result.get("success"),
            },
        )
        return

    # 直接是用例快照
    case_snapshot = parse_case_run_snapshot(parsed)
    if case_snapshot is None:
        raise ValueError("once 模式用例快照为空")
    case_result = await case_runner.run(case_snapshot)
    logger.info(
        "once mode case result",
        {
            "taskId": case_result.task_id,
            "status": case_result.status,
            "success": case_result.success,
        },
    )


async def _run_poll(config: WorkerConfig) -> None:
    """
    执行 poll 模式

    Args:
        config: 工作配置

    Raises:
        ValueError: 缺少控制面地址时抛出
    """
    if not config.control_plane_base_url:
        raise ValueError("poll 模式缺少 config.toml 中的 [control_plane].base_url")

    # 创建客户端和运行器
    control_plane_client = ControlPlaneClient(config)
    case_runner = UiCaseRunner(config, control_plane_client)
    suite_runner = UiSuiteRunner(config, control_plane_client)

    # 创建轮询器
    from .poller.task_poller import TaskPoller

    poller = TaskPoller(config, control_plane_client, case_runner, suite_runner)

    # 开始轮询
    await poller.start()


async def _main() -> None:
    """主函数"""
    config = load_config()
    case_runner = UiCaseRunner(config)
    suite_runner = UiSuiteRunner(config)

    if config.mode == "once":
        await _run_once(config.snapshot_file, case_runner, suite_runner)
        return

    await _run_poll(config)


async def _run_with_shutdown_signals() -> None:
    """Run the worker and translate process signals into async cancellation."""
    loop = asyncio.get_running_loop()
    worker_task = asyncio.create_task(_main(), name="test-worker")
    shutdown_signal: signal.Signals | None = None
    registered_signals: list[signal.Signals] = []

    def request_shutdown(received_signal: signal.Signals) -> None:
        nonlocal shutdown_signal
        if shutdown_signal is not None or worker_task.done():
            return
        shutdown_signal = received_signal
        logger.info(
            "test worker shutdown requested",
            {
                "signal": received_signal.name,
            },
        )
        worker_task.cancel()

    for handled_signal in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                handled_signal,
                request_shutdown,
                handled_signal,
            )
            registered_signals.append(handled_signal)
        except (NotImplementedError, RuntimeError):
            # Windows event loops do not support add_signal_handler. There,
            # asyncio.run and the KeyboardInterrupt fallback handle Ctrl+C.
            continue

    try:
        await worker_task
    except asyncio.CancelledError:
        if shutdown_signal is None:
            raise
        logger.info(
            "test worker shutdown completed",
            {
                "signal": shutdown_signal.name,
            },
        )
    finally:
        for handled_signal in registered_signals:
            loop.remove_signal_handler(handled_signal)


def main() -> None:
    """入口函数"""
    # 本地开发不注入探针端口，此时不启动 health server。
    health_port = health_port_from_env()
    health_server = HealthServer(port=health_port) if health_port is not None else None
    if health_server is not None:
        health_server.start()
    try:
        asyncio.run(_run_with_shutdown_signals())
    except KeyboardInterrupt:
        logger.info("test worker interrupted by user")
    except Exception as e:
        logger.error("test worker process fatal error", {"error": str(e)})
        sys.exit(1)
    finally:
        if health_server is not None:
            health_server.stop()


class _NoopControlPlaneClient:
    """No-op client for collection once mode."""

    def report_api_collection_item_started(
        self, task_id: str, item_id: str, payload: dict
    ) -> None:
        return None

    def report_api_collection_item_completed(
        self, task_id: str, item_id: str, payload: dict
    ) -> None:
        return None


if __name__ == "__main__":
    main()
