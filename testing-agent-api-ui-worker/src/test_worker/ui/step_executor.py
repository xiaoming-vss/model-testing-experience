"""
步骤执行器模块
执行 UI 测试步骤
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Page

from .locator import resolve_locator
from .templates import render_template
from ..contracts.types import UiStepDefinition, UiStepRunResult


@dataclass
class StepExecutionContext:
    """步骤执行上下文"""
    page: Page
    artifact_dir: str
    default_step_timeout_ms: int


def now_iso() -> str:
    """获取当前时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()


def duration_ms(started_at: float) -> int:
    """
    计算持续时间（毫秒）

    Args:
        started_at: 开始时间戳

    Returns:
        持续时间毫秒数
    """
    return int((datetime.now().timestamp() - started_at) * 1000)


def _build_step_name(step: UiStepDefinition, fallback_order: int) -> str:
    """
    构建步骤名称

    Args:
        step: 步骤定义
        fallback_order: 备用序号

    Returns:
        步骤名称
    """
    if step.step_name and step.step_name.strip():
        return step.step_name.strip()
    return f"Step {fallback_order}"


def _sanitize_filename(filename: str) -> str:
    """
    清理文件名中的非法字符

    Args:
        filename: 原始文件名

    Returns:
        清理后的文件名
    """
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", filename)


async def _take_named_screenshot(page: Page, artifact_dir: str, filename: str) -> str:
    """
    截取命名截图

    Args:
        page: Playwright 页面对象
        artifact_dir: 产物目录
        filename: 文件名

    Returns:
        截图文件路径
    """
    sanitized = _sanitize_filename(filename)
    full_path = Path(artifact_dir) / sanitized
    full_path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(full_path), full_page=True)
    return str(full_path)


async def _wait_for_text(page: Page, step: UiStepDefinition, expected_text: str, timeout_ms: int) -> str:
    """
    等待文本出现

    Args:
        page: Playwright 页面对象
        step: 步骤定义
        expected_text: 期望的文本
        timeout_ms: 超时时间（毫秒）

    Returns:
        实际文本

    Raises:
        ValueError: 超时时抛出
    """
    if not expected_text:
        raise ValueError("wait_text 缺少 expect_value 或 operation_value")

    locator = resolve_locator(page, step)
    started_at = datetime.now().timestamp()
    timeout_sec = timeout_ms / 1000

    while datetime.now().timestamp() - started_at < timeout_sec:
        try:
            current_text = (await locator.text_content()) or ""
            current_text = current_text.strip()
            if expected_text in current_text:
                return current_text
        except Exception:
            pass
        await page.wait_for_timeout(200)

    raise ValueError(f"等待文本超时，期望包含: {expected_text}")


def _assert_by_comparator(actual_value: str, expected_value: str, comparator: str) -> None:
    """
    根据比较器进行断言

    Args:
        actual_value: 实际值
        expected_value: 期望值
        comparator: 比较器类型

    Raises:
        AssertionError: 断言失败时抛出
    """
    if comparator == "eq":
        if actual_value != expected_value:
            raise AssertionError(f"断言失败，期望等于 \"{expected_value}\"，实际为 \"{actual_value}\"")
    else:
        if expected_value not in actual_value:
            raise AssertionError(f"断言失败，期望包含 \"{expected_value}\"，实际为 \"{actual_value}\"")


class StepExecutor:
    """步骤执行器类"""

    async def execute(
        self,
        step: UiStepDefinition,
        fallback_order: int,
        context: StepExecutionContext,
    ) -> UiStepRunResult:
        """
        执行步骤

        Args:
            step: 步骤定义
            fallback_order: 备用序号
            context: 执行上下文

        Returns:
            步骤运行结果
        """
        started_at_iso = now_iso()
        started_at = datetime.now().timestamp()
        step_name = _build_step_name(step, fallback_order)
        timeout_ms = step.timeout_ms or context.default_step_timeout_ms
        keyword = step.keyword.lower()

        # 渲染模板变量
        resolved_step = UiStepDefinition(
            keyword=step.keyword,
            order_no=step.order_no,
            step_name=step.step_name,
            locator_type=step.locator_type,
            locator_value=render_template(step.locator_value),
            operation_value=render_template(step.operation_value),
            expect_value=render_template(step.expect_value),
            timeout_ms=step.timeout_ms,
            continue_on_failure=step.continue_on_failure,
            enabled=step.enabled,
            description=step.description,
            comparator=step.comparator,
        )

        try:
            if keyword == "open":
                await context.page.goto(resolved_step.operation_value or "", timeout=timeout_ms)
            elif keyword == "reload":
                await context.page.reload(timeout=timeout_ms)
            elif keyword == "click":
                await resolve_locator(context.page, resolved_step).click(timeout=timeout_ms)
            elif keyword == "dblclick":
                await resolve_locator(context.page, resolved_step).dblclick(timeout=timeout_ms)
            elif keyword == "input":
                await resolve_locator(context.page, resolved_step).fill(resolved_step.operation_value or "", timeout=timeout_ms)
            elif keyword == "clear":
                await resolve_locator(context.page, resolved_step).fill("", timeout=timeout_ms)
            elif keyword == "press":
                await resolve_locator(context.page, resolved_step).press(resolved_step.operation_value or "", timeout=timeout_ms)
            elif keyword == "wait_visible":
                await resolve_locator(context.page, resolved_step).wait_for(state="visible", timeout=timeout_ms)
            elif keyword == "wait_hidden":
                await resolve_locator(context.page, resolved_step).wait_for(state="hidden", timeout=timeout_ms)
            elif keyword == "wait_text":
                return await self._execute_wait_text(context, resolved_step, fallback_order, started_at_iso, started_at, timeout_ms)
            elif keyword == "assert_text":
                return await self._execute_assert_text(context, resolved_step, fallback_order, started_at_iso, started_at)
            elif keyword == "assert_visible":
                if not resolved_step.operation_value:
                    raise ValueError("assert_visible 缺少 operation_value")
                try:
                    visible_timeout_ms = int(resolved_step.operation_value)
                except ValueError as exc:
                    raise ValueError("assert_visible 的 operation_value 必须为毫秒整数") from exc
                if visible_timeout_ms <= 0:
                    raise ValueError("assert_visible 的 operation_value 必须为正整数")
                await resolve_locator(context.page, resolved_step).wait_for(
                    state="visible",
                    timeout=visible_timeout_ms,
                )
            elif keyword == "assert_url":
                return self._execute_assert_url(context, resolved_step, fallback_order, started_at_iso, started_at)
            elif keyword == "screenshot":
                return await self._execute_screenshot(context, resolved_step, fallback_order, started_at_iso, started_at)
            elif keyword == "sleep":
                await context.page.wait_for_timeout(int(resolved_step.operation_value or "0"))
            else:
                raise ValueError(f"暂不支持的关键字: {keyword}")

            return UiStepRunResult(
                order_no=step.order_no or fallback_order,
                step_name=step_name,
                keyword=keyword,
                status="success",
                success=True,
                started_at=started_at_iso,
                finished_at=now_iso(),
                duration_ms=duration_ms(started_at),
            )
        except Exception as e:
            raise Exception(str(e)) from e

    async def capture_failure_screenshot(
        self,
        page: Page,
        artifact_dir: str,
        fallback_order: int,
    ) -> str:
        """
        捕获失败截图

        Args:
            page: Playwright 页面对象
            artifact_dir: 产物目录
            fallback_order: 步骤序号

        Returns:
            截图文件路径
        """
        return await _take_named_screenshot(page, artifact_dir, f"step-{fallback_order}-failed.png")

    async def capture_step_screenshot(
        self,
        page: Page,
        artifact_dir: str,
        fallback_order: int,
    ) -> str:
        """捕获步骤执行后截图"""
        return await _take_named_screenshot(page, artifact_dir, f"step-{fallback_order}.png")

    async def _execute_wait_text(
        self,
        context: StepExecutionContext,
        step: UiStepDefinition,
        fallback_order: int,
        started_at_iso: str,
        started_at: float,
        timeout_ms: int,
    ) -> UiStepRunResult:
        """执行 wait_text 步骤"""
        step_name = _build_step_name(step, fallback_order)
        expected_text = step.expect_value or step.operation_value or ""
        actual_value = await _wait_for_text(context.page, step, expected_text, timeout_ms)

        return UiStepRunResult(
            order_no=step.order_no or fallback_order,
            step_name=step_name,
            keyword="wait_text",
            status="success",
            success=True,
            started_at=started_at_iso,
            finished_at=now_iso(),
            duration_ms=duration_ms(started_at),
            actual_value=actual_value,
        )

    async def _execute_assert_text(
        self,
        context: StepExecutionContext,
        step: UiStepDefinition,
        fallback_order: int,
        started_at_iso: str,
        started_at: float,
    ) -> UiStepRunResult:
        """执行 assert_text 步骤"""
        step_name = _build_step_name(step, fallback_order)
        if not step.operation_value:
            raise ValueError("assert_text 缺少 operation_value")
        locator = resolve_locator(context.page, step)
        actual_value = ((await locator.text_content()) or "").strip()
        comparator = step.comparator or "contains"
        _assert_by_comparator(actual_value, step.operation_value, comparator)

        return UiStepRunResult(
            order_no=step.order_no or fallback_order,
            step_name=step_name,
            keyword="assert_text",
            status="success",
            success=True,
            started_at=started_at_iso,
            finished_at=now_iso(),
            duration_ms=duration_ms(started_at),
            actual_value=actual_value,
        )

    def _execute_assert_url(
        self,
        context: StepExecutionContext,
        step: UiStepDefinition,
        fallback_order: int,
        started_at_iso: str,
        started_at: float,
    ) -> UiStepRunResult:
        """执行 assert_url 步骤"""
        step_name = _build_step_name(step, fallback_order)
        actual_value = context.page.url
        comparator = step.comparator or "contains"
        if not step.operation_value:
            raise ValueError("assert_url 缺少 operation_value")
        _assert_by_comparator(actual_value, step.operation_value, comparator)

        return UiStepRunResult(
            order_no=step.order_no or fallback_order,
            step_name=step_name,
            keyword="assert_url",
            status="success",
            success=True,
            started_at=started_at_iso,
            finished_at=now_iso(),
            duration_ms=duration_ms(started_at),
            actual_value=actual_value,
        )

    async def _execute_screenshot(
        self,
        context: StepExecutionContext,
        step: UiStepDefinition,
        fallback_order: int,
        started_at_iso: str,
        started_at: float,
    ) -> UiStepRunResult:
        """执行 screenshot 步骤"""
        step_name = _build_step_name(step, fallback_order)
        screenshot_name = step.operation_value
        if not screenshot_name or not screenshot_name.strip():
            screenshot_name = f"step-{step.order_no or fallback_order}.png"
        screenshot_path = await _take_named_screenshot(context.page, context.artifact_dir, screenshot_name)

        return UiStepRunResult(
            order_no=step.order_no or fallback_order,
            step_name=step_name,
            keyword="screenshot",
            status="success",
            success=True,
            started_at=started_at_iso,
            finished_at=now_iso(),
            duration_ms=duration_ms(started_at),
            screenshot_path=screenshot_path,
        )
