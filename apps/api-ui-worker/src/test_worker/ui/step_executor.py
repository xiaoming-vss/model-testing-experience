"""
步骤执行器模块
执行 UI 测试步骤
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from .extraction import (
    SaveRule,
    extract_value,
    fill_inherited_locator,
    parse_save_rules,
)
from .locator import resolve_locator
from .templates import RenderContext, referenced_names, render_field
from .variables import StepVariableResolver
from ..contracts.types import UiStepDefinition, UiStepRunResult


class StepExecutionFailure(Exception):
    """Raised when a step fails after some extraction rules already succeeded."""

    def __init__(
        self,
        message: str,
        *,
        save_results: list[dict[str, Any]] | None = None,
        used_variables: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.save_results = list(save_results or [])
        self.used_variables = list(used_variables or [])


@dataclass
class StepExecutionContext:
    """步骤执行上下文"""

    page: Page
    artifact_dir: str
    default_step_timeout_ms: int
    variables: StepVariableResolver | None = None
    # 由私密变量填充的输入框，截图时作为遮罩传入。
    masked_locators: list[Any] = field(default_factory=list)


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


async def _take_named_screenshot(
    page: Page, artifact_dir: str, filename: str, mask: list[Any] | None = None
) -> str:
    """
    截取命名截图

    Args:
        page: Playwright 页面对象
        artifact_dir: 产物目录
        filename: 文件名
        mask: 需要遮罩的定位

    Returns:
        截图文件路径
    """
    sanitized = _sanitize_filename(filename)
    # The control plane only accepts png/zip/mp4/webm artifacts for UI runs and
    # Playwright encodes by extension. A screenshot name without .png (or with
    # a non-png suffix) would otherwise fail the upload ticket with 400.
    path = Path(sanitized)
    sanitized = path.with_suffix(".png").name if path.suffix else f"{path.name}.png"
    full_path = Path(artifact_dir) / sanitized
    full_path.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {}
    if mask:
        kwargs["mask"] = mask
    await page.screenshot(path=str(full_path), full_page=True, **kwargs)
    return str(full_path)


async def _wait_for_text(
    page: Page, step: UiStepDefinition, expected_text: str, timeout_ms: int
) -> str:
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


def _assert_by_comparator(
    actual_value: str, expected_value: str, comparator: str
) -> None:
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
            raise AssertionError(
                f'断言失败，期望等于 "{expected_value}"，实际为 "{actual_value}"'
            )
    else:
        if expected_value not in actual_value:
            raise AssertionError(
                f'断言失败，期望包含 "{expected_value}"，实际为 "{actual_value}"'
            )


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
        if step.missing_fields:
            raise ValueError("步骤存在未补齐的 missingFields，禁止执行")
        started_at_iso = now_iso()
        started_at = datetime.now().timestamp()
        step_name = _build_step_name(step, fallback_order)
        timeout_ms = step.timeout_ms or context.default_step_timeout_ms
        keyword = step.keyword.lower()
        order_no = step.order_no or fallback_order

        # 收集本步骤引用的命名变量并一次性取回；内置函数 $xxx 不经过控制面。
        names = referenced_names(
            step.locator_value, step.operation_value, step.expect_value
        )
        if names:
            if context.variables is None:
                raise ValueError(
                    "当前运行模式无法读取环境变量；请使用 poll 模式或补齐快照变量"
                )
            values: dict[str, str] = await context.variables.resolve(names)
        else:
            values = {}
        secret_names = set(getattr(values, "secret_names", set()) or set())
        used_variables = [
            {
                "name": name,
                "value": values.get(name, ""),
                "secret": name in secret_names,
            }
            for name in names
            if name in values
        ]

        builtins: dict[str, str] = {}
        locator_type = step.locator_type or ""
        resolved_step = UiStepDefinition(
            keyword=step.keyword,
            order_no=step.order_no,
            step_name=step.step_name,
            locator_type=step.locator_type,
            locator_value=render_field(
                step.locator_value,
                values,
                RenderContext("locatorValue", locator_type, keyword, builtins),
            ),
            operation_value=render_field(
                step.operation_value,
                values,
                RenderContext("operationValue", locator_type, keyword, builtins),
            ),
            expect_value=render_field(
                step.expect_value,
                values,
                RenderContext("expectValue", locator_type, keyword, builtins),
            ),
            timeout_ms=step.timeout_ms,
            continue_on_failure=step.continue_on_failure,
            enabled=step.enabled,
            description=step.description,
            comparator=step.comparator,
        )

        actual_value: str | None = None
        screenshot_path: str | None = None

        try:
            save_rules = fill_inherited_locator(
                parse_save_rules(step.save_to), resolved_step
            )
        except Exception as exc:
            raise StepExecutionFailure(str(exc), used_variables=used_variables) from exc

        try:
            if keyword == "open":
                await context.page.goto(
                    resolved_step.operation_value or "", timeout=timeout_ms
                )
            elif keyword == "reload":
                await context.page.reload(timeout=timeout_ms)
            elif keyword == "click":
                await resolve_locator(context.page, resolved_step).click(
                    timeout=timeout_ms
                )
            elif keyword == "dblclick":
                await resolve_locator(context.page, resolved_step).dblclick(
                    timeout=timeout_ms
                )
            elif keyword == "input":
                locator = resolve_locator(context.page, resolved_step)
                await locator.fill(
                    resolved_step.operation_value or "", timeout=timeout_ms
                )
                if secret_names.intersection(referenced_names(step.operation_value)):
                    # 私密变量填充的输入框在截图里遮罩，避免回看时泄露。
                    context.masked_locators.append(locator)
            elif keyword == "clear":
                await resolve_locator(context.page, resolved_step).fill(
                    "", timeout=timeout_ms
                )
            elif keyword == "press":
                await resolve_locator(context.page, resolved_step).press(
                    resolved_step.operation_value or "", timeout=timeout_ms
                )
            elif keyword == "wait_visible":
                await resolve_locator(context.page, resolved_step).wait_for(
                    state="visible", timeout=timeout_ms
                )
            elif keyword == "wait_hidden":
                await resolve_locator(context.page, resolved_step).wait_for(
                    state="hidden", timeout=timeout_ms
                )
            elif keyword == "wait_text":
                actual_value = await self._perform_wait_text(
                    context, resolved_step, timeout_ms
                )
            elif keyword == "assert_text":
                actual_value = await self._perform_assert_text(context, resolved_step)
            elif keyword == "assert_visible":
                if not resolved_step.operation_value:
                    raise ValueError("assert_visible 缺少 operation_value")
                try:
                    visible_timeout_ms = int(resolved_step.operation_value)
                except ValueError as exc:
                    raise ValueError(
                        "assert_visible 的 operation_value 必须为毫秒整数"
                    ) from exc
                if visible_timeout_ms <= 0:
                    raise ValueError("assert_visible 的 operation_value 必须为正整数")
                await resolve_locator(context.page, resolved_step).wait_for(
                    state="visible",
                    timeout=visible_timeout_ms,
                )
            elif keyword == "assert_hidden":
                if not resolved_step.operation_value:
                    raise ValueError("assert_hidden 缺少 operation_value")
                try:
                    hidden_timeout_ms = int(resolved_step.operation_value)
                except ValueError as exc:
                    raise ValueError(
                        "assert_hidden 的 operation_value 必须为毫秒整数"
                    ) from exc
                if hidden_timeout_ms <= 0:
                    raise ValueError("assert_hidden 的 operation_value 必须为正整数")
                await resolve_locator(context.page, resolved_step).wait_for(
                    state="hidden",
                    timeout=hidden_timeout_ms,
                )
            elif keyword == "assert_url":
                actual_value = self._perform_assert_url(resolved_step, context)
            elif keyword == "screenshot":
                screenshot_path = await self._perform_screenshot(
                    context, resolved_step, order_no
                )
            elif keyword == "sleep":
                await context.page.wait_for_timeout(
                    int(resolved_step.operation_value or "0")
                )
            else:
                raise ValueError(f"暂不支持的关键字: {keyword}")
        except Exception as e:
            raise StepExecutionFailure(str(e), used_variables=used_variables) from e

        save_results = await self._run_extractions(
            save_rules, order_no, timeout_ms, context, resolved_step, used_variables
        )

        return UiStepRunResult(
            order_no=order_no,
            step_name=step_name,
            keyword=keyword,
            status="success",
            success=True,
            started_at=started_at_iso,
            finished_at=now_iso(),
            duration_ms=duration_ms(started_at),
            actual_value=actual_value,
            screenshot_path=screenshot_path,
            save_results=save_results,
            used_variables=used_variables,
        )

    async def _run_extractions(
        self,
        rules: list[SaveRule],
        order_no: int,
        timeout_ms: int,
        context: StepExecutionContext,
        resolved_step: UiStepDefinition,
        used_variables: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Run `saveTo` rules in order; each successful value is written back immediately."""
        save_results: list[dict[str, Any]] = []
        for rule in rules:
            try:
                value, used_default = await extract_value(
                    context.page, resolved_step, rule, timeout_ms
                )
                if context.variables is None:
                    raise ValueError("当前运行模式无法写入环境变量；请使用 poll 模式")
                await context.variables.write(rule.name, value, order_no)
            except Exception as exc:
                raise StepExecutionFailure(
                    str(exc),
                    save_results=save_results,
                    used_variables=used_variables,
                ) from exc
            save_results.append(
                {
                    "name": rule.name,
                    "value": value,
                    "source": rule.source,
                    "usedDefault": used_default,
                }
            )
        return save_results

    async def capture_failure_screenshot(
        self,
        page: Page,
        artifact_dir: str,
        fallback_order: int,
        mask: list[Any] | None = None,
    ) -> str:
        """
        捕获失败截图

        Args:
            page: Playwright 页面对象
            artifact_dir: 产物目录
            fallback_order: 步骤序号
            mask: 需要遮罩的定位

        Returns:
            截图文件路径
        """
        return await _take_named_screenshot(
            page, artifact_dir, f"step-{fallback_order}-failed.png", mask
        )

    async def capture_step_screenshot(
        self,
        page: Page,
        artifact_dir: str,
        fallback_order: int,
        mask: list[Any] | None = None,
    ) -> str:
        """捕获步骤执行后截图"""
        return await _take_named_screenshot(
            page, artifact_dir, f"step-{fallback_order}.png", mask
        )

    async def _perform_wait_text(
        self,
        context: StepExecutionContext,
        step: UiStepDefinition,
        timeout_ms: int,
    ) -> str:
        """执行 wait_text 步骤并返回匹配到的文本"""
        expected_text = step.expect_value or step.operation_value or ""
        return await _wait_for_text(context.page, step, expected_text, timeout_ms)

    async def _perform_assert_text(
        self,
        context: StepExecutionContext,
        step: UiStepDefinition,
    ) -> str:
        """执行 assert_text 步骤并返回实际文本"""
        if not step.operation_value:
            raise ValueError("assert_text 缺少 operation_value")
        locator = resolve_locator(context.page, step)
        actual_value = ((await locator.text_content()) or "").strip()
        comparator = step.comparator or "contains"
        _assert_by_comparator(actual_value, step.operation_value, comparator)
        return actual_value

    def _perform_assert_url(
        self, step: UiStepDefinition, context: StepExecutionContext
    ) -> str:
        """执行 assert_url 步骤并返回实际 URL"""
        actual_value = context.page.url
        comparator = step.comparator or "contains"
        if not step.operation_value:
            raise ValueError("assert_url 缺少 operation_value")
        _assert_by_comparator(actual_value, step.operation_value, comparator)
        return actual_value

    async def _perform_screenshot(
        self,
        context: StepExecutionContext,
        step: UiStepDefinition,
        fallback_order: int,
    ) -> str:
        """执行 screenshot 步骤并返回截图路径"""
        screenshot_name = step.operation_value
        if not screenshot_name or not screenshot_name.strip():
            screenshot_name = f"step-{fallback_order}.png"
        return await _take_named_screenshot(
            context.page,
            context.artifact_dir,
            screenshot_name,
            context.masked_locators,
        )
