from __future__ import annotations

import asyncio

import pytest

from test_worker.contracts.types import UiStepDefinition
from test_worker.control_plane.client import (
    ControlPlaneRequestError,
    ExecutionLeaseLost,
)
from test_worker.ui.extraction import parse_save_rules
from test_worker.ui.step_executor import (
    StepExecutionContext,
    StepExecutionFailure,
    StepExecutor,
)
from test_worker.ui.variables import StepVariableResolver


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


@pytest.mark.parametrize("call", ["resolve", "write"])
@pytest.mark.parametrize("status, ends_lease", [(403, True), (409, True), (400, False)])
def test_only_a_lost_lease_escapes_the_step_as_more_than_a_failure(
    call, status, ends_lease
):
    class Client:
        def resolve_ui_run_variables(self, task_id, run_id, names):
            raise ControlPlaneRequestError("POST", "/variables:resolve", status)

        def write_ui_run_variables(self, task_id, run_id, items):
            raise ControlPlaneRequestError("POST", "/variables:write", status)

    class Page:
        url = "https://app.example.test/"

    async def run():
        resolver = StepVariableResolver(Client(), "task-1", "run-1")
        context = StepExecutionContext(
            page=Page(),
            artifact_dir="",
            default_step_timeout_ms=5000,
            variables=resolver,
        )
        if call == "resolve":
            step = UiStepDefinition(
                keyword="input", locator_value="#name", operation_value="{{recordName}}"
            )
            await StepExecutor().execute(step, 1, context)
        rules = parse_save_rules([{"name": "token", "source": "url"}])
        await StepExecutor()._run_extractions(
            rules, 1, 5000, context, UiStepDefinition(keyword="open"), []
        )

    # A rejected request fails the step; a lost lease must stop the whole run instead.
    if ends_lease:
        expected = ExecutionLeaseLost
    else:
        expected = StepExecutionFailure if call == "write" else ControlPlaneRequestError
    with pytest.raises(expected):
        asyncio.run(run())
