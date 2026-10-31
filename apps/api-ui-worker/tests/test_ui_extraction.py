from __future__ import annotations

import asyncio

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from test_worker.contracts.types import UiStepDefinition
from test_worker.ui.step_executor import (
    StepExecutionContext,
    StepExecutionFailure,
    StepExecutor,
)
from test_worker.ui.variables import ResolvedVariables


class FakePage:
    def __init__(self, url: str = "http://web.example.test/orders/31") -> None:
        self.url = url
        self.reloaded = 0

    async def reload(self, timeout: int | None = None) -> None:
        self.reloaded += 1

    async def screenshot(self, **kwargs) -> None:
        return None


class FakeLocator:
    def __init__(
        self,
        *,
        text: str | None = "",
        value: str = "",
        attribute: str | None = None,
        count: int = 1,
        missing: bool = False,
    ) -> None:
        self._text = text
        self._value = value
        self._attribute = attribute
        self._count = count
        self._missing = missing

    async def wait_for(self, state: str, timeout: int) -> None:
        if self._missing:
            raise PlaywrightTimeoutError("timeout")

    async def count(self) -> int:
        return self._count

    async def text_content(self, timeout: int | None = None) -> str | None:
        return self._text

    async def input_value(self, timeout: int | None = None) -> str:
        return self._value

    async def get_attribute(self, name: str, timeout: int | None = None) -> str | None:
        return self._attribute

    async def fill(self, value: str, timeout: int) -> None:
        return None

    async def click(self, timeout: int) -> None:
        return None


class FakeResolver:
    def __init__(
        self, values: dict[str, str] | None = None, secrets: list[str] | None = None
    ):
        self.values = values or {}
        self.secrets = secrets or []
        self.writes: list[tuple[str, str, int | None]] = []

    async def resolve(self, names: list[str]) -> ResolvedVariables:
        return ResolvedVariables(
            {name: self.values[name] for name in names if name in self.values},
            self.secrets,
        )

    async def write(self, name: str, value: str, order_no: int | None = None) -> None:
        self.writes.append((name, value, order_no))


def _context(page: FakePage, resolver: FakeResolver) -> StepExecutionContext:
    return StepExecutionContext(
        page=page,  # type: ignore[arg-type]
        artifact_dir="",
        default_step_timeout_ms=5000,
        variables=resolver,  # type: ignore[arg-type]
    )


def test_save_to_reads_text_and_writes_back_immediately(monkeypatch) -> None:
    resolver = FakeResolver()
    monkeypatch.setattr(
        "test_worker.ui.extraction.resolve_locator",
        lambda page, step: FakeLocator(text=" 订单 31 "),
    )
    step = UiStepDefinition(
        keyword="reload",
        order_no=5,
        save_to=[
            {
                "name": "taskId",
                "source": "text",
                "locatorType": "xpath",
                "locatorValue": "//td[1]",
            }
        ],
    )

    result = asyncio.run(
        StepExecutor().execute(step, 1, _context(FakePage(), resolver))
    )

    assert resolver.writes == [("taskId", "订单 31", 5)]
    assert result.save_results == [
        {"name": "taskId", "value": "订单 31", "source": "text", "usedDefault": False}
    ]


def test_save_to_uses_default_value_only_for_zero_match(monkeypatch) -> None:
    resolver = FakeResolver()
    monkeypatch.setattr(
        "test_worker.ui.extraction.resolve_locator",
        lambda page, step: FakeLocator(missing=True),
    )
    step = UiStepDefinition(
        keyword="reload",
        save_to=[
            {
                "name": "taskId",
                "source": "value",
                "locatorType": "css",
                "locatorValue": "#task",
                "defaultValue": "0",
            }
        ],
    )

    result = asyncio.run(
        StepExecutor().execute(step, 1, _context(FakePage(), resolver))
    )

    assert resolver.writes == [("taskId", "0", 1)]
    assert result.save_results[0]["usedDefault"] is True


def test_save_to_failure_keeps_prior_write_and_fails_step(monkeypatch) -> None:
    resolver = FakeResolver()
    locators = iter([FakeLocator(text="first"), FakeLocator(text="dup", count=2)])
    monkeypatch.setattr(
        "test_worker.ui.extraction.resolve_locator",
        lambda page, step: next(locators),
    )
    step = UiStepDefinition(
        keyword="reload",
        order_no=3,
        save_to=[
            {
                "name": "first",
                "source": "text",
                "locatorType": "css",
                "locatorValue": "#a",
            },
            {
                "name": "second",
                "source": "text",
                "locatorType": "css",
                "locatorValue": "#b",
            },
        ],
    )

    with pytest.raises(StepExecutionFailure, match="收窄定位") as error:
        asyncio.run(StepExecutor().execute(step, 1, _context(FakePage(), resolver)))

    assert resolver.writes == [("first", "first", 3)]
    assert [item["name"] for item in error.value.save_results] == ["first"]


def test_save_to_requires_locator_inheritance_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "test_worker.ui.extraction.resolve_locator",
        lambda page, step: FakeLocator(text="x"),
    )
    step = UiStepDefinition(
        keyword="reload",
        save_to=[{"name": "taskId", "source": "text"}],
    )

    with pytest.raises(StepExecutionFailure, match="没有可继承的定位"):
        asyncio.run(
            StepExecutor().execute(step, 1, _context(FakePage(), FakeResolver()))
        )


def test_save_to_inherits_rendered_step_locator(monkeypatch) -> None:
    resolver = FakeResolver({"id": "42"})
    captured: list[tuple[str | None, str | None]] = []

    def fake_extraction_locator(page, step):
        captured.append((step.locator_type, step.locator_value))
        return FakeLocator(text="value")

    monkeypatch.setattr(
        "test_worker.ui.step_executor.resolve_locator",
        lambda page, step: FakeLocator(),
    )
    monkeypatch.setattr(
        "test_worker.ui.extraction.resolve_locator", fake_extraction_locator
    )
    step = UiStepDefinition(
        keyword="click",
        locator_type="css",
        locator_value="#row-{{id}}",
        save_to=[{"name": "row", "source": "text"}],
    )

    result = asyncio.run(
        StepExecutor().execute(step, 1, _context(FakePage(), resolver))
    )

    assert captured == [("css", "#row-42")]
    assert result.save_results[0]["value"] == "value"


def test_secret_input_is_registered_for_screenshot_mask(monkeypatch) -> None:
    locator = FakeLocator()

    monkeypatch.setattr(
        "test_worker.ui.step_executor.resolve_locator",
        lambda page, step: locator,
    )
    resolver = FakeResolver({"password": "secret"}, secrets=["password"])
    context = _context(FakePage(), resolver)
    step = UiStepDefinition(
        keyword="input",
        locator_value="#password",
        operation_value="{{password}}",
    )

    asyncio.run(StepExecutor().execute(step, 1, context))

    assert context.masked_locators == [locator]
