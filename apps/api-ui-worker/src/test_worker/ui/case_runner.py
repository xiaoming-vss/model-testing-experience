"""
用例运行器模块
执行单个测试用例
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from ..contracts.types import (
    UiCaseRunResult,
    UiCaseRunSnapshot,
    UiCaseRunStatus,
    UiStepDefinition,
    UiStepRunResult,
    WorkerConfig,
)
from ..core import logger
from ..control_plane.client import ExecutionLeaseLost
from .browser_cancellation import (
    await_browser_operation,
    await_browser_start,
    close_browser_resource,
)
from .browser_options import (
    context_options_from_suite,
    default_step_timeout_from_suite,
    launch_options_from_suite,
    screenshot_policy_from_suite,
)
from .playwright_session import playwright_session
from .step_executor import StepExecutionContext, StepExecutor, now_iso
from .step_normalizer import normalize_case_steps
from .step_results import build_failed_step_result
from .step_progress import report_steps
from .variables import StepVariableResolver


def _normalize_steps(snapshot: UiCaseRunSnapshot) -> list[UiStepDefinition]:
    """
    规范化步骤列表

    Args:
        snapshot: 用例运行快照

    Returns:
        步骤定义列表

    Raises:
        ValueError: stepsJson 格式错误时抛出
    """
    return normalize_case_steps(snapshot.case)


def _build_artifact_dir(config: WorkerConfig, snapshot: UiCaseRunSnapshot) -> str:
    """
    构建产物目录

    Args:
        config: 工作配置
        snapshot: 用例运行快照

    Returns:
        产物目录路径
    """
    return str(Path(config.artifacts_root_dir) / snapshot.run_id)


class UiCaseRunner:
    """用例运行器类"""

    def __init__(
        self, config: WorkerConfig, control_plane_client: Any | None = None
    ) -> None:
        """
        初始化用例运行器

        Args:
            config: 工作配置
            control_plane_client: 控制面客户端（可选，用于逐步解析环境变量）
        """
        self._config = config
        self._control_plane_client = control_plane_client
        self._step_executor = StepExecutor()

    async def run(self, snapshot: UiCaseRunSnapshot) -> UiCaseRunResult:
        """
        执行单个测试用例

        Args:
            snapshot: 用例运行快照

        Returns:
            用例运行结果
        """
        started_at_iso = now_iso()
        started_at = datetime.now().timestamp()

        # 创建产物目录
        artifact_dir = _build_artifact_dir(self._config, snapshot)
        Path(artifact_dir).mkdir(parents=True, exist_ok=True)

        # 规范化步骤
        steps = [
            step for step in _normalize_steps(snapshot) if step.enabled is not False
        ]
        steps.sort(key=lambda s: s.order_no or 0)

        # 启动浏览器
        async with playwright_session(async_playwright, snapshot.task_id) as p:
            launch_options = launch_options_from_suite(snapshot.suite)
            context_options = context_options_from_suite(snapshot.suite)
            logger.info(
                "ui browser launch options",
                {
                    "taskId": snapshot.task_id,
                    "runId": snapshot.run_id,
                    "headless": launch_options.get("headless"),
                    "ignoreHTTPSErrors": context_options.get("ignore_https_errors"),
                },
            )
            browser = await await_browser_start(p.chromium.launch(**launch_options))

            trace_path = ""
            step_results: list[UiStepRunResult] = []
            error_message = ""
            status: UiCaseRunStatus = "success"
            success = True
            current_url = ""
            context = None
            trace_stopped = False

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
                resolver = (
                    StepVariableResolver(
                        self._control_plane_client, snapshot.task_id, snapshot.run_id
                    )
                    if self._control_plane_client is not None
                    else None
                )
                execution_context = StepExecutionContext(
                    page=page,
                    artifact_dir=artifact_dir,
                    default_step_timeout_ms=default_step_timeout,
                    variables=resolver,
                )
                screenshot_policy = screenshot_policy_from_suite(snapshot.suite)

                # 执行步骤
                for index, step in enumerate(steps):
                    fallback_order = step.order_no or index + 1
                    step_started_at_iso = now_iso()
                    step_started_at = datetime.now().timestamp()
                    await report_steps(
                        self._control_plane_client,
                        snapshot.task_id,
                        None,
                        step_results,
                        step,
                        fallback_order,
                        step_started_at_iso,
                    )

                    try:
                        result = await await_browser_operation(
                            self._step_executor.execute(
                                step, fallback_order, execution_context
                            ),
                            page,
                        )
                        if screenshot_policy == "after_each_step":
                            screenshot_path = await await_browser_operation(
                                self._step_executor.capture_step_screenshot(
                                    page,
                                    artifact_dir,
                                    fallback_order,
                                    execution_context.masked_locators,
                                ),
                                page,
                            )
                            result = result.__class__(
                                **{
                                    **result.__dict__,
                                    "screenshot_path": screenshot_path,
                                }
                            )
                        step_results.append(result)
                        await report_steps(
                            self._control_plane_client,
                            snapshot.task_id,
                            None,
                            step_results,
                        )
                    except ExecutionLeaseLost:
                        raise
                    except Exception as e:
                        message = str(e)
                        failed_result = build_failed_step_result(
                            step,
                            fallback_order,
                            step_started_at_iso,
                            step_started_at,
                            message,
                            save_results=getattr(e, "save_results", None),
                            used_variables=getattr(e, "used_variables", None),
                        )

                        # 捕获失败截图
                        if screenshot_policy in ("on_failure", "after_each_step"):
                            try:
                                screenshot_path = await await_browser_operation(
                                    self._step_executor.capture_failure_screenshot(
                                        page,
                                        artifact_dir,
                                        fallback_order,
                                        execution_context.masked_locators,
                                    ),
                                    page,
                                )
                                failed_result = failed_result.__class__(
                                    **{
                                        **failed_result.__dict__,
                                        "screenshot_path": screenshot_path,
                                    }
                                )
                            except Exception as capture_error:
                                logger.warn(
                                    "capture failure screenshot error",
                                    {
                                        "taskId": snapshot.task_id,
                                        "stepOrderNo": fallback_order,
                                        "error": str(capture_error),
                                    },
                                )

                        step_results.append(failed_result)
                        await report_steps(
                            self._control_plane_client,
                            snapshot.task_id,
                            None,
                            step_results,
                        )
                        success = False
                        status = "failed"
                        error_message = message

                        if not step.continue_on_failure:
                            break

                # 获取当前 URL
                current_url = page.url

                # 保存 trace
                if self._config.trace_enabled:
                    trace_path = str(Path(artifact_dir) / "trace.zip")
                    await context.tracing.stop(path=trace_path)
                    trace_stopped = True

            except ExecutionLeaseLost:
                raise
            except Exception as e:
                success = False
                status = "error"
                error_message = str(e)

            finally:
                # 停止 trace
                if context and self._config.trace_enabled and not trace_stopped:
                    candidate = str(Path(artifact_dir) / "trace.zip")
                    if await close_browser_resource(
                        context.tracing.stop(path=candidate), snapshot.task_id, "trace"
                    ):
                        trace_path = candidate

                # 关闭上下文
                if context:
                    await close_browser_resource(
                        context.close(), snapshot.task_id, "context"
                    )

                # 关闭浏览器
                closed = await close_browser_resource(
                    browser.close(), snapshot.task_id, "browser"
                )
                if not closed and sys.exc_info()[0] is None:
                    raise RuntimeError("浏览器关闭异常，请检查 Worker 资源后手动重试")

        return UiCaseRunResult(
            task_id=snapshot.task_id,
            run_id=snapshot.run_id,
            case_id=snapshot.case.case_id,
            status=status,
            success=success,
            started_at=started_at_iso,
            finished_at=now_iso(),
            duration_ms=int((datetime.now().timestamp() - started_at) * 1000),
            step_results=step_results,
            current_url=current_url or None,
            trace_path=trace_path or None,
            error_message=error_message or None,
        )
