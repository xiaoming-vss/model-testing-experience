"""Small template runtime for API snapshots."""

from __future__ import annotations

import json
import re
from typing import Any


_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def load_runtime_vars(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return {}
    return {str(key): "" if value is None else str(value) for key, value in parsed.items()}


def dump_runtime_vars(vars_map: dict[str, str]) -> str:
    return json.dumps(vars_map, ensure_ascii=False, separators=(",", ":"))


def render_template(value: str | None, vars_map: dict[str, str]) -> str:
    if not value:
        return ""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return vars_map.get(key, match.group(0))

    return _TEMPLATE_PATTERN.sub(replace, value)


def render_json_map(raw: str | None, vars_map: dict[str, str]) -> dict[str, str]:
    if not raw:
        return {}
    rendered_raw = render_template(raw, vars_map)
    parsed = json.loads(rendered_raw)
    if not isinstance(parsed, dict):
        return {}
    return {str(key): "" if value is None else str(value) for key, value in parsed.items()}


def render_json_body(raw: str | None, vars_map: dict[str, str]) -> tuple[Any, str]:
    if not raw:
        return None, ""
    rendered_raw = render_template(raw, vars_map)
    parsed = json.loads(rendered_raw)
    return parsed, json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
