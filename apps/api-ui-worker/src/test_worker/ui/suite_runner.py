"""
测试集运行器模块
执行测试集（多个用例）
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from ..contracts.types import (
    UiStepDefinition,
    UiSuiteItemRunResult,
    UiSuiteRunItemSnapshot,
    UiSuiteRunResult,
    UiTestSuiteRunSnapshot,
    WorkerConfig,
)
from ..control_plane.client import ControlPlaneClient
from ..core import logger
from .browser_options import (
    context_options_from_suite,
    default_step_timeout_from_suite,
    launch_options_from_suite,
    screenshot_policy_from_suite,
)
from .step_executor import StepExecutionContext, StepExecutor, now_iso
from .step_normalizer import normalize_case_steps
from .step_results import build_failed_step_result


def _normalize_steps(item: UiSuiteRunItemSnapshot) -> list[UiStepDefinition]:
    """
    规范化步骤列表

    Args:
        item: 测试集运行项快照

    Returns:
        步骤定义列表

    Raises:
        ValueError: stepsJson 格式错误时抛出
    """
    return normalize_case_steps(item.case)


def _build_artifact_dir(config: WorkerConfig, snapshot: UiTestSuiteRunSnapshot) -> str:
    """
    构建产物目录

    Args:
        config: 工作配置
        snapshot: 测试集运行快照

    Returns:
        产物目录路径
    """
    return str(Path(config.artifacts_root_dir) / snapshot.run_id)


def _build_case_artifact_dir(root_artifact_dir: str, item: UiSuiteRunItemSnapshot) -> str:
    """
    构建用例产物目录

    Args:
        root_artifact_dir: 根产物目录
        item: 测试集运行项快照

    Returns:
        用例产物目录路径
    """
    return str(Path(root_artifact_dir) / item.item_id)


def _build_skipped_item_result(
    item: UiSuiteRunItemSnapshot,
    run_id: str,
    reason: str,
) -> UiSuiteItemRunResult:
    """
    构建跳过的测试集项结果

    Args:
        item: 测试集运行项快照
        run_id: 运行 ID
        reason: 跳过原因

    Returns:
        测试集项运行结果
    """
    return UiSuiteItemRunResult(
        item_id=item.item_id,
        run_id=run_id,
        case_id=item.case.case_id,
        status="skipped",
        success=False,
        finished_at=now_iso(),
        duration_ms=0,
        error_message=reason,
        step_results=[],
    )


class UiSuiteRunner:
    """测试集运行器类"""

    def __init__(self, config: WorkerConfig, control_plane_client: ControlPlaneClient | None = None) -> None:
        """
        初始化测试集运行器

        Args:
            config: 工作配置
            control_plane_client: 控制面客户端（可选）
        """
        self._config = config
        self._control_plane_client = control_plane_client
        self._step_executor = StepExecutor()

    async def run(self, snapshot: UiTestSuiteRunSnapshot) -> UiSuiteRunResult:
        """
        执行测试集

        Args:
            snapshot: 测试集运行快照

        Returns:
            测试集运行结果
        """
        started_at_iso = now_iso()
        started_at = datetime.now().timestamp()

        # 创建产物目录
        artifact_dir = _build_artifact_dir(self._config, snapshot)
        Path(artifact_dir).mkdir(parents=True, exist_ok=True)

        # 排序测试项
        items = sorted(snapshot.items, key=lambda i: i.case.order_no or 0)

        # 启动浏览器
        async with async_playwright() as p:
            launch_options = launch_options_from_suite(snapshot.suite)
            context_options = context_options_from_suite(snapshot.suite)
            logger.info("ui browser launch options", {
                "taskId": snapshot.task_id,
                "runId": snapshot.run_id,
                "suite": snapshot.suite.__dict__ if snapshot.suite else None,
                "launchOptions": launch_options,
                "contextOptions": context_options,
            })
            browser = await p.chromium.launch(**launch_options)

            trace_path = ""
            error_message = ""
            current_url = ""
            context = None
            trace_stopped = False
            has_failed = False
            has_error = False
            halted = False

            try:
                # 创建浏览器上下文
                context_options = context_options_from_suite(snapshot.suite)
                context = await browser.new_context(**context_options)

                # 开启 trace
                if self._config.trace_enabled:
                    await context.tracing.start(screenshots=True, snapshots=True)

                # 创建页面
                page = await context.new_page()
                default_step_timeout = default_step_timeout_from_suite(snapshot.suite)
                execution_context = StepExecutionContext(
                    page=page,
                    artifact_dir=artifact_dir,
                    default_step_timeout_ms=default_step_timeout,
                )

                # 执行测试项
                for item in items:
                    # 跳过未启用的用例
                    if item.case.enabled is False:
                        await self._report_suite_item_completed(
                            snapshot.task_id,
                            item.item_id,
                            _build_skipped_item_result(item, snapshot.run_id, "用例未启用"),
                        )
                        continue

                    # 跳过因前置失败而中止的用例
                    if halted:
                        await self._report_suite_item_completed(
                            snapshot.task_id,
                            item.item_id,
                            _build_skipped_item_result(item, snapshot.run_id, "前置用例失败且未开启 continueOnFailure"),
                        )
                        continue

                    # 上报用例开始
                    case_started_at = now_iso()
                    await self._report_suite_item_started(snapshot.task_id, item.item_id, {
                        "runId": snapshot.run_id,
                        "caseId": item.case.case_id,
                        "startedAt": case_started_at,
                    })

                    # 执行用例
                    result = await self._run_suite_item(snapshot, item, execution_context, case_started_at)
                    await self._report_suite_item_completed(snapshot.task_id, item.item_id, result)

                    # 更新状态
                    if result.status == "failed":
                        has_failed = True
                        halted = not item.continue_on_failure
                    if result.status == "error":
                        has_error = True
                        halted = not item.continue_on_failure

                # 获取当前 URL
                current_url = page.url

                # 保存 trace
                if self._config.trace_enabled:
                    trace_path = str(Path(artifact_dir) / "trace.zip")
                    await context.tracing.stop(path=trace_path)
                    trace_stopped = True

            except Exception as e:
                has_error = True
                error_message = str(e)

            finally:
                # 停止 trace
                if context and self._config.trace_enabled and not trace_stopped:
                    try:
                        trace_path = str(Path(artifact_dir) / "trace.zip")
                        await context.tracing.stop(path=trace_path)
                    except Exception as trace_error:
                        logger.warn("stop suite trace error", {
                            "taskId": snapshot.task_id,
                            "error": str(trace_error),
                        })

                # 关闭上下文
                if context:
                    try:
                        await context.close()
                    except Exception as context_error:
                        logger.warn("close suite browser context error", {
                            "taskId": snapshot.task_id,
                            "error": str(context_error),
                        })

                # 关闭浏览器
                await browser.close()

        # 计算最终状态
        if has_error:
            status = "error"
        elif has_failed:
            status = "failed"
        else:
            status = "success"

        return UiSuiteRunResult(
            task_id=snapshot.task_id,
            run_id=snapshot.run_id,
            suite_id=snapshot.suite.suite_id if snapshot.suite else "",
            status=status,
            success=status == "success",
            started_at=started_at_iso,
            finished_at=now_iso(),
            duration_ms=int((datetime.now().timestamp() - started_at) * 1000),
            current_url=current_url or None,
            trace_path=trace_path or None,
            error_message=error_message or None,
        )

    async def _run_suite_item(
        self,
        snapshot: UiTestSuiteRunSnapshot,
        item: UiSuiteRunItemSnapshot,
        execution_context: StepExecutionContext,
        started_at_iso: str,
    ) -> UiSuiteItemRunResult:
        """
        执行测试集项

        Args:
            snapshot: 测试集运行快照
            item: 测试集运行项快照
            execution_context: 执行上下文
            started_at_iso: 开始时间 ISO 格式

        Returns:
            测试集项运行结果
        """
        case_started_at = datetime.now().timestamp()

        # 创建用例产物目录
        case_artifact_dir = _build_case_artifact_dir(execution_context.artifact_dir, item)
        Path(case_artifact_dir).mkdir(parents=True, exist_ok=True)

        # 规范化步骤
        steps = [
            step for step in _normalize_steps(item)
            if step.enabled is not False
        ]
        steps.sort(key=lambda s: s.order_no or 0)

        # 创建用例执行上下文
        case_execution_context = StepExecutionContext(
            page=execution_context.page,
            artifact_dir=case_artifact_dir,
            default_step_timeout_ms=execution_context.default_step_timeout_ms,
        )
        screenshot_policy = screenshot_policy_from_suite(snapshot.suite)

        step_results = []
        error_message = ""
        status = "success"
        success = True
        current_url = ""

        try:
            # 执行步骤
            for index, step in enumerate(steps):
                fallback_order = step.order_no or index + 1
                step_started_at_iso = now_iso()
                step_started_at = datetime.now().timestamp()

                try:
                    result = await self._step_executor.execute(step, fallback_order, case_execution_context)
                    if screenshot_policy == "after_each_step":
                        screenshot_path = await self._step_executor.capture_step_screenshot(
                            execution_context.page, case_artifact_dir, fallback_order
                        )
                        result = result.__class__(
                            **{**result.__dict__, "screenshot_path": screenshot_path}
                        )
                    step_results.append(result)
                except Exception as e:
                    message = str(e)
                    failed_result = build_failed_step_result(
                        step, fallback_order, step_started_at_iso, step_started_at, message
                    )

                    # 捕获失败截图
                    if screenshot_policy in ("on_failure", "after_each_step"):
                        try:
                            page = execution_context.page
                            screenshot_path = await self._step_executor.capture_failure_screenshot(
                                page, case_artifact_dir, fallback_order
                            )
                            failed_result = failed_result.__class__(
                                **{**failed_result.__dict__, "screenshot_path": screenshot_path}
                            )
                        except Exception as capture_error:
                            logger.warn("capture suite failure screenshot error", {
                                "taskId": snapshot.task_id,
                                "itemId": item.item_id,
                                "stepOrderNo": fallback_order,
                                "error": str(capture_error),
                            })

                    step_results.append(failed_result)
                    success = False
                    status = "failed"
                    error_message = message

                    if not step.continue_on_failure:
                        break

            # 获取当前 URL
            current_url = execution_context.page.url

        except Exception as e:
            success = False
            status = "error"
            error_message = str(e)

        return UiSuiteItemRunResult(
            item_id=item.item_id,
            run_id=snapshot.run_id,
            case_id=item.case.case_id,
            status=status,
            success=success,
            started_at=started_at_iso,
            finished_at=now_iso(),
            duration_ms=int((datetime.now().timestamp() - case_started_at) * 1000),
            step_results=step_results,
            current_url=current_url or None,
            error_message=error_message or None,
        )


    async def _report_suite_item_started(self, task_id: str, item_id: str, payload: dict) -> None:
        """上报测试集项开始"""
        if not self._control_plane_client:
            return
        from ..contracts.types import UiSuiteItemStartedPayload
        self._control_plane_client.report_suite_item_started(
            task_id,
            item_id,
            UiSuiteItemStartedPayload(
                run_id=payload.get("runId", ""),
                case_id=payload.get("caseId", ""),
                started_at=payload.get("startedAt", ""),
            ),
        )

    async def _report_suite_item_completed(self, task_id: str, item_id: str, payload: UiSuiteItemRunResult) -> None:
        """上报测试集项完成"""
        if not self._control_plane_client:
            return
        self._control_plane_client.report_suite_item_completed(task_id, item_id, payload)






