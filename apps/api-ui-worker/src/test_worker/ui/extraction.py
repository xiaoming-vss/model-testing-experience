"""Post-step value extraction (`saveTo`) helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ..contracts.types import UiStepDefinition
from .locator import resolve_locator

EXTRACT_SOURCES = frozenset({"text", "value", "attribute", "url"})
MAX_NAME_LENGTH = 120
FORBIDDEN_NAME_CHARACTERS = frozenset("{}|")
RESERVED_NAMES = frozenset({"baseUrl"})


@dataclass
class SaveRule:
    name: str
    source: str
    locator_type: str | None = None
    locator_value: str | None = None
    attribute: str | None = None
    default_value: str | None = None
    trim: bool = True


def parse_save_rules(raw: Any) -> list[SaveRule]:
    """Validate the raw `saveTo` payload defensively before touching the browser."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("saveTo 必须是数组")

    rules: list[SaveRule] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"saveTo 第 {index} 项必须是对象")
        name = _validate_name(str(item.get("name") or ""), index)
        if name in seen:
            raise ValueError(f"saveTo 第 {index} 项的变量名重复：{name}")
        seen.add(name)

        source = str(item.get("source") or "").strip().lower()
        if source not in EXTRACT_SOURCES:
            raise ValueError(
                f"saveTo {name} 的 source 仅支持 text / value / attribute / url"
            )

        rule = SaveRule(name=name, source=source)
        attribute = item.get("attribute")
        if source == "attribute":
            if not isinstance(attribute, str) or not attribute.strip():
                raise ValueError(
                    f"saveTo {name} 在 source=attribute 时必须填写 attribute"
                )
            rule.attribute = attribute.strip()
        elif attribute is not None:
            raise ValueError(f"saveTo {name} 的 attribute 仅用于 source=attribute")

        if source == "url":
            if (
                item.get("locatorType") is not None
                or item.get("locatorValue") is not None
            ):
                raise ValueError(f"saveTo {name} 在 source=url 时不能填写定位")
        else:
            locator_type = item.get("locatorType")
            locator_value = item.get("locatorValue")
            if locator_type is None and locator_value is None:
                # 省略定位时继承本步骤，运行前由 fill_inherited_locator 补齐。
                pass
            elif locator_type is None or locator_value is None:
                raise ValueError(
                    f"saveTo {name} 的 locatorType 与 locatorValue 必须同时填写"
                )
            else:
                if not isinstance(locator_type, str) or not locator_type.strip():
                    raise ValueError(f"saveTo {name} 必须填写 locatorType")
                if not isinstance(locator_value, str) or not locator_value.strip():
                    raise ValueError(f"saveTo {name} 必须填写 locatorValue")
                if "{{" in locator_value:
                    raise ValueError(f"saveTo {name} 的定位不支持变量")
                rule.locator_type = locator_type.strip().lower()
                rule.locator_value = locator_value

        default_value = item.get("defaultValue")
        if default_value is not None:
            if not isinstance(default_value, str):
                raise ValueError(f"saveTo {name} 的 defaultValue 必须是字符串")
            rule.default_value = default_value

        trim = item.get("trim")
        if trim is not None:
            if not isinstance(trim, bool):
                raise ValueError(f"saveTo {name} 的 trim 必须是布尔值")
            rule.trim = trim

        rules.append(rule)

    return rules


def fill_inherited_locator(
    rules: list[SaveRule], step: UiStepDefinition
) -> list[SaveRule]:
    """Apply "omit the locator to inherit the step's own locator" at execution time."""
    step_locator_type = (step.locator_type or "").strip().lower()
    step_locator_value = step.locator_value
    for rule in rules:
        if rule.source == "url":
            continue
        if rule.locator_type is None and rule.locator_value is None:
            if not step_locator_type or not step_locator_value:
                raise ValueError(
                    f"saveTo {rule.name} 未填写定位，且本步骤没有可继承的定位"
                )
            rule.locator_type = step_locator_type
            rule.locator_value = step_locator_value
    return rules


def extraction_locator(page: Page, step: UiStepDefinition, rule: SaveRule) -> Locator:
    return resolve_locator(
        page,
        UiStepDefinition(
            keyword=step.keyword,
            locator_type=rule.locator_type,
            locator_value=rule.locator_value,
        ),
    )


async def extract_value(
    page: Page, step: UiStepDefinition, rule: SaveRule, timeout_ms: int
) -> tuple[str, bool]:
    """Read one value; return (value, used_default)."""
    if rule.source == "url":
        return page.url, False

    locator = extraction_locator(page, step, rule)
    try:
        await locator.wait_for(state="attached", timeout=timeout_ms)
    except PlaywrightTimeoutError as exc:
        if rule.default_value is not None:
            return rule.default_value, True
        raise ValueError(f"提取 {rule.name} 失败：未找到匹配元素") from exc

    count = await locator.count()
    if count > 1:
        raise ValueError(f"提取 {rule.name} 失败：匹配到 {count} 个元素，请收窄定位")

    try:
        if rule.source == "text":
            value = await locator.text_content(timeout=timeout_ms)
            value = (value or "").strip() if rule.trim else (value or "")
        elif rule.source == "value":
            value = await locator.input_value(timeout=timeout_ms)
        else:
            value = await locator.get_attribute(
                rule.attribute or "", timeout=timeout_ms
            )
    except PlaywrightTimeoutError as exc:
        raise ValueError(f"提取 {rule.name} 失败：读取超时") from exc

    if value is None or value == "":
        if rule.default_value is not None:
            return rule.default_value, True
        return "", False
    return value, False


def _validate_name(name: str, index: int) -> str:
    value = name.strip()
    if not value:
        raise ValueError(f"saveTo 第 {index} 项缺少变量名")
    if len(value) > MAX_NAME_LENGTH:
        raise ValueError(f"saveTo {value} 的变量名不能超过 {MAX_NAME_LENGTH} 个字符")
    if FORBIDDEN_NAME_CHARACTERS.intersection(value):
        raise ValueError(f"saveTo {value} 的变量名不能包含 {{ }} 或 |")
    if any(character.isspace() for character in value):
        raise ValueError(f"saveTo {value} 的变量名不能包含空白字符")
    if value.startswith(("$", "data.")):
        raise ValueError(f"saveTo {value} 的变量名不能以 $ 或 data. 开头")
    if value in RESERVED_NAMES:
        raise ValueError(f"saveTo 不能写入内置变量 {value}")
    return value
