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
from .core.artifact_server import ArtifactHttpServer
from .control_plane.client import ControlPlaneClient
from .contracts.types import (
    UiCaseRunSnapshot,
    UiTestSuiteRunSnapshot,
    UiWorkerTaskSnapshotResponse,
    WorkerConfig,
)
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
            result = await ApiCaseRunner().run(parsed["caseRun"])
            logger.info("once mode api case result", {
                "taskId": result.get("taskId"),
                "status": result.get("status"),
                "success": result.get("success"),
            })
            return

        if parsed.get("taskType") == "api_collection_run" and parsed.get("collectionRun"):
            result = await ApiCollectionRunner(_NoopControlPlaneClient()).run(parsed["collectionRun"])
            logger.info("once mode api collection result", {
                "taskId": result.get("taskId"),
                "status": result.get("status"),
                "success": result.get("success"),
            })
            return

        snapshot = UiWorkerTaskSnapshotResponse(
            task_type=parsed.get("taskType", "case_debug"),
            case_run=_parse_case_run_snapshot(parsed.get("caseRun")) if "caseRun" in parsed else None,
            suite_run=_parse_suite_run_snapshot(parsed.get("suiteRun")) if "suiteRun" in parsed else None,
        )

        if snapshot.task_type == "suite_run" and snapshot.suite_run:
            result = await suite_runner.run(snapshot.suite_run)
            logger.info("once mode suite result", {
                "taskId": result.task_id,
                "status": result.status,
                "success": result.success,
            })
            return

        if snapshot.task_type == "case_debug" and snapshot.case_run:
            result = await case_runner.run(snapshot.case_run)
            logger.info("once mode case result", {
                "taskId": result.task_id,
                "status": result.status,
                "success": result.success,
            })
            return

        raise ValueError("once 模式快照缺少可执行内容")

    if "collectionRunId" in parsed and "items" in parsed:
        result = await ApiCollectionRunner(_NoopControlPlaneClient()).run(parsed)
        logger.info("once mode api collection result", {
            "taskId": result.get("taskId"),
            "status": result.get("status"),
            "success": result.get("success"),
        })
        return

    # 直接是测试集快照
    if "items" in parsed:
        snapshot = _parse_suite_run_snapshot(parsed)
        result = await suite_runner.run(snapshot)
        logger.info("once mode suite result", {
            "taskId": result.task_id,
            "status": result.status,
            "success": result.success,
        })
        return

    if "request" in parsed and "caseId" in parsed:
        result = await ApiCaseRunner().run(parsed)
        logger.info("once mode api case result", {
            "taskId": result.get("taskId"),
            "status": result.get("status"),
            "success": result.get("success"),
        })
        return

    # 直接是用例快照
    snapshot = _parse_case_run_snapshot(parsed)
    result = await case_runner.run(snapshot)
    logger.info("once mode case result", {
        "taskId": result.task_id,
        "status": result.status,
        "success": result.success,
    })


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
    case_runner = UiCaseRunner(config)
    suite_runner = UiSuiteRunner(config, control_plane_client)

    # 记录 API 契约
    control_plane_client.log_planned_contract()

    # 创建轮询器
    from .poller.task_poller import TaskPoller
    poller = TaskPoller(config, control_plane_client, case_runner, suite_runner)

    # 开始轮询
    artifact_server = None
    try:
        if config.artifacts_base_url:
            artifact_server = ArtifactHttpServer(
                config.artifacts_root_dir,
                config.artifacts_bind_host,
                config.artifacts_port,
            )
            artifact_server.start()
            logger.info("artifact http server started", {
                "bindHost": config.artifacts_bind_host,
                "port": artifact_server.port,
                "baseUrl": config.artifacts_base_url,
                "root": config.artifacts_root_dir,
            })
        await poller.start()
    finally:
        if artifact_server:
            artifact_server.stop()


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
        logger.info("test worker shutdown requested", {
            "signal": received_signal.name,
        })
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
        logger.info("test worker shutdown completed", {
            "signal": shutdown_signal.name,
        })
    finally:
        for handled_signal in registered_signals:
            loop.remove_signal_handler(handled_signal)


def main() -> None:
    """入口函数"""
    try:
        asyncio.run(_run_with_shutdown_signals())
    except KeyboardInterrupt:
        logger.info("test worker interrupted by user")
    except Exception as e:
        logger.error("test worker process fatal error", {"error": str(e)})
        sys.exit(1)


class _NoopControlPlaneClient:
    """No-op client for collection once mode."""

    def report_api_collection_item_started(self, task_id: str, item_id: str, payload: dict) -> None:
        return None

    def report_api_collection_item_completed(self, task_id: str, item_id: str, payload: dict) -> None:
        return None


def _parse_case_run_snapshot(data: dict | None) -> UiCaseRunSnapshot | None:
    """解析用例运行快照"""
    if not data:
        return None

    from .contracts.types import (
        UiBrowserOptionsSnapshot,
        UiBrowserViewport,
        UiCaseSnapshot,
        UiRunOptionsSnapshot,
        UiStepDefinition,
        UiSuiteSnapshot,
    )

    case_data = data.get("case", {})
    steps = None
    if "steps" in case_data and case_data["steps"]:
        steps = [
            UiStepDefinition(
                keyword=s.get("keyword", ""),
                order_no=s.get("orderNo"),
                step_name=s.get("stepName"),
                locator_type=s.get("locatorType"),
                locator_value=s.get("locatorValue"),
                operation_value=s.get("operationValue"),
                expect_value=s.get("expectValue"),
                timeout_ms=s.get("timeoutMs"),
                continue_on_failure=s.get("continueOnFailure"),
                enabled=s.get("enabled"),
                description=s.get("description"),
                comparator=s.get("comparator"),
            )
            for s in case_data["steps"]
        ]

    case = UiCaseSnapshot(
        case_id=case_data.get("caseId", ""),
        name=case_data.get("name", ""),
        suite_id=case_data.get("suiteId"),
        description=case_data.get("description"),
        enabled=case_data.get("enabled"),
        order_no=case_data.get("orderNo"),
        steps_json=case_data.get("stepsJson"),
        steps=steps,
    )

    suite = None
    if "suite" in data and data["suite"]:
        suite_data = data["suite"]
        suite = UiSuiteSnapshot(
            suite_id=suite_data.get("suiteId", ""),
            name=suite_data.get("name", ""),
            headless=suite_data.get("headless"),
            slow_mo_ms=suite_data.get("slowMoMs"),
            viewport_width=suite_data.get("viewportWidth"),
            viewport_height=suite_data.get("viewportHeight"),
            default_step_timeout_ms=suite_data.get("defaultStepTimeoutMs"),
            screenshot_policy=suite_data.get("screenshotPolicy"),
        )

    browser = None
    if "browser" in data and data["browser"]:
        browser_data = data["browser"]
        viewport = None
        if "viewport" in browser_data and browser_data["viewport"]:
            viewport = UiBrowserViewport(
                width=browser_data["viewport"].get("width", 1280),
                height=browser_data["viewport"].get("height", 720),
            )
        browser = UiBrowserOptionsSnapshot(
            headless=browser_data.get("headless"),
            slow_mo_ms=browser_data.get("slowMoMs"),
            viewport=viewport,
        )

    options = None
    if "options" in data and data["options"]:
        options_data = data["options"]
        options = UiRunOptionsSnapshot(
            default_step_timeout_ms=options_data.get("defaultStepTimeoutMs"),
        )

    return UiCaseRunSnapshot(
        task_id=data.get("taskId", ""),
        run_id=data.get("runId", ""),
        case=case,
        suite=suite,
        browser=browser,
        options=options,
    )


def _parse_suite_run_snapshot(data: dict | None) -> UiTestSuiteRunSnapshot | None:
    """解析测试集运行快照"""
    if not data:
        return None

    from .contracts.types import (
        UiBrowserOptionsSnapshot,
        UiBrowserViewport,
        UiCaseSnapshot,
        UiRunOptionsSnapshot,
        UiStepDefinition,
        UiSuiteRunItemSnapshot,
        UiSuiteSnapshot,
    )

    items = []
    for item_data in data.get("items", []):
        case_data = item_data.get("case", {})
        steps = None
        if "steps" in case_data and case_data["steps"]:
            steps = [
                UiStepDefinition(
                    keyword=s.get("keyword", ""),
                    order_no=s.get("orderNo"),
                    step_name=s.get("stepName"),
                    locator_type=s.get("locatorType"),
                    locator_value=s.get("locatorValue"),
                    operation_value=s.get("operationValue"),
                    expect_value=s.get("expectValue"),
                    timeout_ms=s.get("timeoutMs"),
                    continue_on_failure=s.get("continueOnFailure"),
                    enabled=s.get("enabled"),
                    description=s.get("description"),
                    comparator=s.get("comparator"),
                )
                for s in case_data["steps"]
            ]

        case = UiCaseSnapshot(
            case_id=case_data.get("caseId", ""),
            name=case_data.get("name", ""),
            suite_id=case_data.get("suiteId"),
            description=case_data.get("description"),
            enabled=case_data.get("enabled"),
            order_no=case_data.get("orderNo"),
            steps_json=case_data.get("stepsJson"),
            steps=steps,
        )

        items.append(UiSuiteRunItemSnapshot(
            item_id=item_data.get("itemId", ""),
            continue_on_failure=item_data.get("continueOnFailure", False),
            case=case,
        ))

    suite = None
    if "suite" in data and data["suite"]:
        suite_data = data["suite"]
        suite = UiSuiteSnapshot(
            suite_id=suite_data.get("suiteId", ""),
            name=suite_data.get("name", ""),
            headless=suite_data.get("headless"),
            slow_mo_ms=suite_data.get("slowMoMs"),
            viewport_width=suite_data.get("viewportWidth"),
            viewport_height=suite_data.get("viewportHeight"),
            default_step_timeout_ms=suite_data.get("defaultStepTimeoutMs"),
            screenshot_policy=suite_data.get("screenshotPolicy"),
        )

    browser = None
    if "browser" in data and data["browser"]:
        browser_data = data["browser"]
        viewport = None
        if "viewport" in browser_data and browser_data["viewport"]:
            viewport = UiBrowserViewport(
                width=browser_data["viewport"].get("width", 1280),
                height=browser_data["viewport"].get("height", 720),
            )
        browser = UiBrowserOptionsSnapshot(
            headless=browser_data.get("headless"),
            slow_mo_ms=browser_data.get("slowMoMs"),
            viewport=viewport,
        )

    options = None
    if "options" in data and data["options"]:
        options_data = data["options"]
        options = UiRunOptionsSnapshot(
            default_step_timeout_ms=options_data.get("defaultStepTimeoutMs"),
        )

    return UiTestSuiteRunSnapshot(
        task_id=data.get("taskId", ""),
        run_id=data.get("runId", ""),
        items=items,
        suite=suite,
        browser=browser,
        options=options,
    )


if __name__ == "__main__":
    main()

