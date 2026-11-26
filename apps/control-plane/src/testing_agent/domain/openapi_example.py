"""Placeholder request and response examples derived from JSON Schema."""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

MAX_EXAMPLE_DEPTH = 8
MAX_EXAMPLE_ITEMS = 10
MAX_STRING_LENGTH = 64
SAMPLE_UUID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
_FORMAT_VALUES = {
    "uuid": SAMPLE_UUID,
    "date-time": "2026-11-23T10:00:00Z",
    "date": "2026-11-23",
    "time": "10:00:00",
    "email": "user@example.com",
    "uri": "https://example.com",
    "url": "https://example.com",
    "hostname": "example.com",
    "ipv4": "127.0.0.1",
    "ipv6": "::1",
    "password": "string",
}
_MISSING = object()


def generate_example(schema: Any) -> Any | None:
    """Derive a placeholder example from a request body or response JSON Schema.

    Values written in the document win: ``default``, ``const``, ``example``, ``examples`` and
    ``enum``. Every other field gets a type placeholder that respects length and range
    constraints. Optional fields are listed as well, and a nullable field takes its non-null
    branch. ``pattern`` is not evaluated, so a placeholder may still need editing before it
    satisfies a format requirement. The result depends only on ``schema``, which keeps re-imports
    of an unchanged document stable. Returns ``None`` when the schema does not describe a value.
    """
    value = _sample(schema, 0)
    return None if value is _MISSING else value


def _sample(schema: Any, depth: int) -> Any:
    if not isinstance(schema, dict) or depth > MAX_EXAMPLE_DEPTH:
        return _MISSING
    node = _flatten(schema)
    for value in _document_values(node):
        if _json_native(value):
            return value
    return _placeholder(node, depth)


def _document_values(node: dict[str, Any]) -> Iterator[Any]:
    for keyword in ("default", "const", "example"):
        if keyword in node:
            yield node[keyword]
    for keyword in ("examples", "enum"):
        values = node.get(keyword)
        if isinstance(values, list):
            # A nullable enum such as [null, "asc", "desc"] reads better without the null.
            yield from [value for value in values if value is not None] + [
                value for value in values if value is None
            ]


def _placeholder(node: dict[str, Any], depth: int) -> Any:
    kind = _type(node)
    if kind == "object":
        return _object(node, depth)
    if kind == "array":
        return _array(node, depth)
    if kind == "string":
        return _string(node)
    if kind == "integer":
        return _number(node, 1)
    if kind == "number":
        return _number(node, 1.5)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return _MISSING


def _object(node: dict[str, Any], depth: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    properties = node.get("properties")
    if isinstance(properties, dict):
        for name, child in properties.items():
            value = _sample(child, depth + 1)
            if value is not _MISSING:
                result[str(name)] = value
    # A dictionary field describes its values in additionalProperties; show one sample entry.
    extra = node.get("additionalProperties")
    if isinstance(extra, dict) and "key" not in result:
        value = _sample(extra, depth + 1)
        if value is not _MISSING:
            result["key"] = value
    return result


def _array(node: dict[str, Any], depth: int) -> list[Any]:
    items = node.get("items")
    if not isinstance(items, dict):
        return []
    value = _sample(items, depth + 1)
    if value is _MISSING:
        return []
    min_items = _length(node.get("minItems"))
    return [value for _ in range(min(MAX_EXAMPLE_ITEMS, max(1, min_items or 1)))]


def _string(node: dict[str, Any]) -> str:
    formatted = _FORMAT_VALUES.get(str(node.get("format") or ""))
    min_length = _length(node.get("minLength"))
    max_length = _length(node.get("maxLength"))
    if formatted is not None:
        return formatted[:max_length] if max_length is not None else formatted
    candidate = "string"
    if max_length is not None and max_length < len(candidate):
        return candidate[:max_length]
    target = min(min_length or len(candidate), MAX_STRING_LENGTH)
    if max_length is not None:
        target = min(target, max_length)
    while len(candidate) < target:
        candidate += "-string"
    return candidate[:max_length] if max_length is not None else candidate


def _number(node: dict[str, Any], base: int | float) -> int | float:
    value: int | float = base
    minimum = _lower_bound(node)
    maximum = _upper_bound(node)
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    multiple = node.get("multipleOf")
    if isinstance(multiple, (int, float)) and not isinstance(multiple, bool) and multiple > 0:
        value = math.ceil(value / multiple) * multiple
    return value


def _lower_bound(node: dict[str, Any]) -> int | float | None:
    exclusive, minimum = node.get("exclusiveMinimum"), _bound(node.get("minimum"))
    if isinstance(exclusive, (int, float)) and not isinstance(exclusive, bool):
        return exclusive + 1
    if exclusive is True and minimum is not None:
        return minimum + 1
    return minimum


def _upper_bound(node: dict[str, Any]) -> int | float | None:
    exclusive, maximum = node.get("exclusiveMaximum"), _bound(node.get("maximum"))
    if isinstance(exclusive, (int, float)) and not isinstance(exclusive, bool):
        return exclusive - 1
    if exclusive is True and maximum is not None:
        return maximum - 1
    return maximum


def _length(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _bound(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _type(node: dict[str, Any]) -> str | None:
    declared = node.get("type")
    kinds = declared if isinstance(declared, list) else [declared]
    kinds = [kind for kind in kinds if kind != "null"] or kinds
    if kinds and isinstance(kinds[0], str):
        return kinds[0]
    if isinstance(node.get("properties"), dict) or isinstance(
        node.get("additionalProperties"), dict
    ):
        return "object"
    return "array" if "items" in node else None


def _flatten(schema: dict[str, Any]) -> dict[str, Any]:
    """Merges ``allOf`` and keeps the non-null branch of ``anyOf``/``oneOf``."""
    node = dict(schema)
    parts = node.pop("allOf", None)
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict):
                node = _merge(node, part)
    for keyword in ("anyOf", "oneOf"):
        branches = node.pop(keyword, None)
        if not isinstance(branches, list):
            continue
        candidates = [branch for branch in branches if isinstance(branch, dict)]
        if candidates:
            chosen = next(
                (branch for branch in candidates if _type(branch) != "null"), candidates[0]
            )
            node = _merge(node, chosen)
    return node


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = {**base, **extra}
    if isinstance(base.get("properties"), dict) and isinstance(extra.get("properties"), dict):
        merged["properties"] = {**base["properties"], **extra["properties"]}
    return merged


def _json_native(value: Any) -> bool:
    """Whether a YAML-loaded document value can be stored as JSON as-is."""
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_native(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_native(item) for key, item in value.items())
    return False
