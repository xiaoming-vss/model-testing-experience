"""Shared strict JSON and model-response text parsing for task packages."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCED_JSON = re.compile(r"```(?:json)?\s*\n(.*)\n```", re.DOTALL)
_TRUNCATED_REASONS = {"length", "max_tokens", "max_output_tokens"}


def strip_json_fence(raw: str) -> str:
    """Return the JSON body when the whole response is one fenced block."""
    text = raw.strip()
    match = _FENCED_JSON.fullmatch(text)
    return match.group(1).strip() if match else text


def extract_first_json_fence(raw: str) -> str:
    """Return the first fenced JSON block embedded in model prose."""
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw.strip(), re.DOTALL)
    return match.group(1).strip() if match else raw.strip()


def response_finish_reason(response: Any) -> str:
    reason = getattr(response, "finish_reason", None) or getattr(response, "stop_reason", None)
    metadata = getattr(response, "metadata", None)
    if reason is None and isinstance(metadata, dict):
        reason = metadata.get("finish_reason")
    return str(reason or "")


def response_content(response: Any) -> Any:
    return response if isinstance(response, (str, dict)) else getattr(response, "content", None)


def is_truncated(reason: str) -> bool:
    return reason in _TRUNCATED_REASONS


def strict_json(
    raw: str,
    *,
    duplicate_message: str = "JSON 重复字段",
    constant_message: str = "非法 JSON 数值",
) -> Any:
    """Parse JSON while rejecting duplicate keys and non-finite numbers."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"{duplicate_message}: {key}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError(f"{constant_message}: {value}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
