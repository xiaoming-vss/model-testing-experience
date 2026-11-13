"""Validation for post-step extraction rules stored on a UI step (`saveTo`)."""

from __future__ import annotations

from typing import Any

from ui_variable_template import TOKEN_PATTERN, validate_locator_tokens
from variable_names import validate_variable_name

EXTRACT_SOURCES = frozenset({"text", "value", "attribute", "url"})
SAVE_TO_FIELDS = frozenset(
    {"name", "source", "locatorType", "locatorValue", "attribute", "defaultValue", "trim"}
)
LOCATOR_TYPES = frozenset(
    {"css", "xpath", "text", "placeholder", "label", "test_id", "testid", "role"}
)


def normalize_save_to(step: dict[str, Any], *, field_path: str) -> list[dict[str, Any]]:
    """Return the normalized extraction rules or raise ValueError with a precise path."""
    raw = step.get("saveTo")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{field_path}.saveTo 必须是数组")

    step_locator_type = str(step.get("locatorType") or "").strip().lower()
    step_locator_value = step.get("locatorValue")
    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for index, item in enumerate(raw):
        path = f"{field_path}.saveTo[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{path} 必须是对象")
        unknown = set(item) - SAVE_TO_FIELDS
        if unknown:
            raise ValueError(f"{path} 包含未知字段：{'、'.join(sorted(unknown))}")

        try:
            name = validate_variable_name(str(item.get("name") or ""))
        except ValueError as exc:
            raise ValueError(f"{path}.name {exc}") from exc
        if name in seen_names:
            raise ValueError(f"{path}.name 在同一步骤内重复：{name}")
        seen_names.add(name)

        source = str(item.get("source") or "").strip().lower()
        if source not in EXTRACT_SOURCES:
            allowed = " | ".join(sorted(EXTRACT_SOURCES))
            raise ValueError(f"{path}.source 仅支持 {allowed}")

        entry: dict[str, Any] = {"name": name, "source": source}
        attribute = item.get("attribute")
        if source == "attribute":
            if not isinstance(attribute, str) or not attribute.strip():
                raise ValueError(f"{path}.attribute 在 source=attribute 时不能为空")
            entry["attribute"] = attribute.strip()
        elif attribute is not None:
            raise ValueError(f"{path}.attribute 仅用于 source=attribute")

        if source == "url":
            if item.get("locatorType") is not None or item.get("locatorValue") is not None:
                raise ValueError(f"{path} 在 source=url 时不能填写定位")
        else:
            entry.update(_normalize_locator(item, path, step_locator_type, step_locator_value))

        default_value = item.get("defaultValue")
        if default_value is not None:
            if not isinstance(default_value, str):
                raise ValueError(f"{path}.defaultValue 必须是字符串")
            entry["defaultValue"] = default_value

        trim = item.get("trim")
        if trim is not None:
            if not isinstance(trim, bool):
                raise ValueError(f"{path}.trim 必须是布尔值")
            entry["trim"] = trim

        normalized.append(entry)

    return normalized


def _normalize_locator(
    item: dict[str, Any],
    path: str,
    step_locator_type: str,
    step_locator_value: Any,
) -> dict[str, str]:
    locator_type = item.get("locatorType")
    locator_value = item.get("locatorValue")
    if locator_type is None and locator_value is None:
        # 继承保留为“未填写”，执行器在渲染后的步骤定位上补全，步骤定位里的变量因此也能用。
        if (
            not step_locator_type
            or not isinstance(step_locator_value, str)
            or not step_locator_value.strip()
        ):
            raise ValueError(f"{path} 未填写定位，且本步骤没有可继承的定位")
        return {}
    if locator_type is None or locator_value is None:
        raise ValueError(f"{path}.locatorType 与 locatorValue 必须同时填写")

    normalized_type = str(locator_type).strip().lower()
    if normalized_type not in LOCATOR_TYPES:
        allowed = " | ".join(sorted(LOCATOR_TYPES))
        raise ValueError(f"{path}.locatorType 仅支持 {allowed}")
    if not isinstance(locator_value, str) or not locator_value.strip():
        raise ValueError(f"{path}.locatorValue 不能为空")
    if TOKEN_PATTERN.search(locator_value):
        raise ValueError(f"{path}.locatorValue 不支持变量，提取定位必须是静态值")
    try:
        validate_locator_tokens(locator_value, normalized_type)
    except ValueError as exc:
        raise ValueError(f"{path}.locatorValue {exc}") from exc
    return {"locatorType": normalized_type, "locatorValue": locator_value}
