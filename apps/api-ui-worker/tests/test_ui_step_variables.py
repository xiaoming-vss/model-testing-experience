from __future__ import annotations

import asyncio

import pytest

from test_worker.contracts.types import UiStepDefinition
from test_worker.ui.step_executor import StepExecutionContext, StepExecutor


class FakeResolver:
    def __init__(self, values: dict[str, str]):
        self.values = values
        self.calls: list[list[str]] = []

    async def resolve(self, names: list[str]) -> dict[str, str]:
        self.calls.append(list(names))
        return {name: self.values[name] for name in names}


def test_input_renders_environment_value(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeLocator:
        async def fill(self, value: str, timeout: int) -> None:
            captured["value"] = value

    monkeypatch.setattr(
        "test_worker.ui.step_executor.resolve_locator",
        lambda page, step: FakeLocator(),
    )
    resolver = FakeResolver({"recordName": "张三"})
    step = UiStepDefinition(
        keyword="input",
        locator_value="#name",
        operation_value="{{recordName}}",
    )
    context = StepExecutionContext(
        page=object(),
        artifact_dir="",
        default_step_timeout_ms=5000,
        variables=resolver,
    )

    result = asyncio.run(StepExecutor().execute(step, 1, context))

    assert result.success is True
    assert captured["value"] == "张三"
    assert resolver.calls == [["recordName"]]


def test_xpath_locator_is_escaped_before_execution(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeLocator:
        async def click(self, timeout: int) -> None:
            return None

    def fake_resolve(page, step):
        captured["locator"] = step.locator_value
        return FakeLocator()

    monkeypatch.setattr("test_worker.ui.step_executor.resolve_locator", fake_resolve)
    resolver = FakeResolver({"versionName": "O'Neil"})
    step = UiStepDefinition(
        keyword="click",
        locator_type="xpath",
        locator_value="//tr[td={{versionName|xpath}}]/td[3]",
    )
    context = StepExecutionContext(
        page=object(),
        artifact_dir="",
        default_step_timeout_ms=5000,
        variables=resolver,
    )

    asyncio.run(StepExecutor().execute(step, 1, context))

    assert captured["locator"] == '//tr[td="O\'Neil"]/td[3]'


def test_step_with_variables_fails_without_resolver() -> None:
    step = UiStepDefinition(
        keyword="input",
        locator_value="#name",
        operation_value="{{recordName}}",
    )
    context = StepExecutionContext(
        page=object(),
        artifact_dir="",
        default_step_timeout_ms=5000,
    )

    with pytest.raises(Exception, match="环境变量"):
        asyncio.run(StepExecutor().execute(step, 1, context))
