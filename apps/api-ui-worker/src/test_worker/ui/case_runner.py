"""
用例运行器模块
执行单个测试用例
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from ..core import logger
from .browser_options import (
    context_options_from_suite,
    default_step_timeout_from_suite,
    launch_options_from_suite,
    screenshot_policy_from_suite,
)
from .step_executor import StepExecutionContext, StepExecutor, now_iso
from .step_normalizer import normalize_case_steps
from ..contracts.types import (
    UiCaseRunResult,
    UiCaseRunSnapshot,
    UiStepDefinition,
    UiStepRunResult,
    WorkerConfig,
)


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

    def __init__(self, config: WorkerConfig) -> None:
        """
        初始化用例运行器

        Args:
            config: 工作配置
        """
        self._config = config
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
            step for step in _normalize_steps(snapshot)
            if step.enabled is not False
        ]
        steps.sort(key=lambda s: s.order_no or 0)

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
            step_results = []
            error_message = ""
            status = "success"
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
                execution_context = StepExecutionContext(
                    page=page,
                    artifact_dir=artifact_dir,
                    default_step_timeout_ms=default_step_timeout,
                )
                screenshot_policy = screenshot_policy_from_suite(snapshot.suite)

                # 执行步骤
                for index, step in enumerate(steps):
                    fallback_order = step.order_no or index + 1
                    step_started_at_iso = now_iso()
                    step_started_at = datetime.now().timestamp()

                    try:
                        result = await self._step_executor.execute(step, fallback_order, execution_context)
                        if screenshot_policy == "after_each_step":
                            screenshot_path = await self._step_executor.capture_step_screenshot(
                                page, artifact_dir, fallback_order
                            )
                            result = result.__class__(
                                **{**result.__dict__, "screenshot_path": screenshot_path}
                            )
                        step_results.append(result)
                    except Exception as e:
                        message = str(e)
                        failed_result = self._build_failed_step_result(
                            step, fallback_order, step_started_at_iso, step_started_at, message
                        )

                        # 捕获失败截图
                        if screenshot_policy in ("on_failure", "after_each_step"):
                            try:
                                screenshot_path = await self._step_executor.capture_failure_screenshot(
                                    page, artifact_dir, fallback_order
                                )
                                failed_result = failed_result.__class__(
                                    **{**failed_result.__dict__, "screenshot_path": screenshot_path}
                                )
                            except Exception as capture_error:
                                logger.warn("capture failure screenshot error", {
                                    "taskId": snapshot.task_id,
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
                current_url = page.url

                # 保存 trace
                if self._config.trace_enabled:
                    trace_path = str(Path(artifact_dir) / "trace.zip")
                    await context.tracing.stop(path=trace_path)
                    trace_stopped = True

            except Exception as e:
                success = False
                status = "error"
                error_message = str(e)

            finally:
                # 停止 trace
                if context and self._config.trace_enabled and not trace_stopped:
                    try:
                        trace_path = str(Path(artifact_dir) / "trace.zip")
                        await context.tracing.stop(path=trace_path)
                    except Exception as trace_error:
                        logger.warn("stop trace error", {
                            "taskId": snapshot.task_id,
                            "error": str(trace_error),
                        })

                # 关闭上下文
                if context:
                    try:
                        await context.close()
                    except Exception as context_error:
                        logger.warn("close browser context error", {
                            "taskId": snapshot.task_id,
                            "error": str(context_error),
                        })

                # 关闭浏览器
                await browser.close()

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

    def _build_failed_step_result(
        self,
        step: UiStepDefinition,
        fallback_order: int,
        started_at_iso: str,
        started_at: float,
        error_message: str,
    ) -> "UiStepRunResult":
        """
        构建失败的步骤结果

        Args:
            step: 步骤定义
            fallback_order: 备用序号
            started_at_iso: 开始时间 ISO 格式
            started_at: 开始时间戳
            error_message: 错误消息

        Returns:
            步骤运行结果
        """
        from ..contracts.types import UiStepRunResult

        step_name = step.step_name
        if not step_name or not step_name.strip():
            step_name = f"Step {fallback_order}"
        else:
            step_name = step_name.strip()

        return UiStepRunResult(
            order_no=step.order_no or fallback_order,
            step_name=step_name,
            keyword=step.keyword.lower(),
            status="failed",
            success=False,
            started_at=started_at_iso,
            finished_at=now_iso(),
            duration_ms=int((datetime.now().timestamp() - started_at) * 1000),
            error_message=error_message,
        )






