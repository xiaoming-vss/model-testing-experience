from __future__ import annotations

import asyncio

import pytest

from test_worker.contracts.types import UiStepDefinition
from test_worker.ui.step_executor import StepExecutionContext, StepExecutor


def test_assert_text_uses_operation_value_and_ignores_expect_value(monkeypatch) -> None:
    class FakeLocator:
        async def text_content(self) -> str:
            return "操作成功"

    monkeypatch.setattr(
        "test_worker.ui.step_executor.resolve_locator",
        lambda page, step: FakeLocator(),
    )

    step = UiStepDefinition(
        keyword="assert_text",
        locator_value="#result",
        operation_value="操作成功",
        expect_value="不应读取此字段",
        comparator="eq",
    )
    context = StepExecutionContext(
        page=object(),
        artifact_dir="",
        default_step_timeout_ms=5000,
    )

    result = asyncio.run(StepExecutor().execute(step, 1, context))

    assert result.success is True
    assert result.actual_value == "操作成功"


def test_assert_visible_uses_operation_value_as_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeLocator:
        async def wait_for(self, *, state: str, timeout: int) -> None:
            captured["state"] = state
            captured["timeout"] = timeout

    monkeypatch.setattr(
        "test_worker.ui.step_executor.resolve_locator",
        lambda page, step: FakeLocator(),
    )

    step = UiStepDefinition(
        keyword="assert_visible",
        locator_value="#submit",
        operation_value="2500",
        timeout_ms=9000,
    )
    context = StepExecutionContext(
        page=object(),
        artifact_dir="",
        default_step_timeout_ms=5000,
    )

    result = asyncio.run(StepExecutor().execute(step, 1, context))

    assert result.success is True
    assert captured == {"state": "visible", "timeout": 2500}


def test_assert_url_uses_operation_value_and_ignores_expect_value() -> None:
    class FakePage:
        url = "https://example.test/dashboard"

    step = UiStepDefinition(
        keyword="assert_url",
        operation_value="https://example.test/dashboard",
        expect_value="https://wrong.example.test",
        comparator="eq",
    )
    context = StepExecutionContext(
        page=FakePage(),
        artifact_dir="",
        default_step_timeout_ms=5000,
    )

    result = asyncio.run(StepExecutor().execute(step, 1, context))

    assert result.success is True
    assert result.actual_value == "https://example.test/dashboard"


@pytest.mark.parametrize("keyword", ["assert_text", "assert_url"])
def test_assertion_rejects_missing_operation_value(keyword, monkeypatch) -> None:
    class FakeLocator:
        async def text_content(self) -> str:
            return "anything"

    class FakePage:
        url = "https://example.test/dashboard"

    monkeypatch.setattr(
        "test_worker.ui.step_executor.resolve_locator",
        lambda page, step: FakeLocator(),
    )
    step = UiStepDefinition(keyword=keyword, locator_value="#result")
    context = StepExecutionContext(
        page=FakePage(),
        artifact_dir="",
        default_step_timeout_ms=5000,
    )

    with pytest.raises(Exception, match=f"{keyword} 缺少 operation_value"):
        asyncio.run(StepExecutor().execute(step, 1, context))


@pytest.mark.parametrize("operation_value", ["0", "-1"])
def test_assert_visible_rejects_non_positive_timeout(operation_value) -> None:
    step = UiStepDefinition(
        keyword="assert_visible",
        locator_value="#submit",
        operation_value=operation_value,
    )
    context = StepExecutionContext(
        page=object(),
        artifact_dir="",
        default_step_timeout_ms=5000,
    )

    with pytest.raises(Exception, match="必须为正整数"):
        asyncio.run(StepExecutor().execute(step, 1, context))
