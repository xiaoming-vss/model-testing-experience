"""Pure normalization and identity rules for project interface definitions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

ALLOWED_METHODS: tuple[str, ...] = (
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS",
)
BODY_TYPES: tuple[str, ...] = ("none", "json", "form", "raw")
ROW_TYPES: tuple[str, ...] = (
    "string",
    "integer",
    "number",
    "boolean",
    "array",
    "object",
    "file",
)
RowLocation = Literal["header", "path", "query"]

_PATH_PARAM_PATTERN = re.compile(r"\{([^{}]+)\}")
_MULTI_SLASH_PATTERN = re.compile(r"/+")


def normalize_method(value: str) -> str:
    method = str(value or "").strip().upper()
    if method not in ALLOWED_METHODS:
        raise ValueError(f"不支持的 HTTP 方法：{method or '空'}")
    return method


def normalize_path(value: str) -> str:
    path = str(value or "").strip()
    if not path:
        raise ValueError("接口路径不能为空")
    if not path.startswith("/"):
        path = f"/{path}"
    path = _MULTI_SLASH_PATTERN.sub("/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    if any(char.isspace() for char in path):
        raise ValueError("接口路径不能包含空白字符")
    if "?" in path or "#" in path:
        raise ValueError("接口路径不能包含查询串或片段")
    if len(path) > 1024:
        raise ValueError("接口路径不能超过 1024 个字符")
    _path_parameter_names(path)
    return path


def normalize_base_path(value: str) -> str:
    base_path = str(value or "").strip()
    if not base_path:
        return ""
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    base_path = _MULTI_SLASH_PATTERN.sub("/", base_path)
    if len(base_path) > 1 and base_path.endswith("/"):
        base_path = base_path.rstrip("/")
    if any(char.isspace() for char in base_path):
        raise ValueError("base path 不能包含空白字符")
    if "?" in base_path or "#" in base_path:
        raise ValueError("base path 不能包含查询串或片段")
    if len(base_path) > 512:
        raise ValueError("base path 不能超过 512 个字符")
    return base_path


def path_key(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _path_parameter_names(path: str) -> list[str]:
    names: list[str] = []
    for match in _PATH_PARAM_PATTERN.finditer(path):
        name = match.group(1).strip()
        if not name or "/" in name or "{" in name or "}" in name:
            raise ValueError("路径占位符名称不合法")
        if len(name) > 120:
            raise ValueError("路径占位符名称不能超过 120 个字符")
        if name in names:
            raise ValueError(f"路径占位符 {name} 重复出现")
        names.append(name)
    remainder = _PATH_PARAM_PATTERN.sub("", path)
    if "{" in remainder or "}" in remainder:
        raise ValueError("接口路径包含未闭合的占位符")
    return names


def path_parameter_names(path: str) -> list[str]:
    """Return unique placeholder names in first-seen order."""
    return _path_parameter_names(path)


def normalize_tags(values: Iterable[str] | None) -> list[str]:
    tags: list[str] = []
    for raw in values or []:
        tag = str(raw or "").strip()
        if not tag:
            continue
        if len(tag) > 50:
            raise ValueError("单个标签不能超过 50 个字符")
        if tag in tags:
            continue
        tags.append(tag)
    if len(tags) > 20:
        raise ValueError("标签不能超过 20 个")
    return tags


def normalize_rows(
    rows: Iterable[Mapping[str, Any] | Any] | None,
    *,
    location: RowLocation,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows or []:
        row = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
        name = str(row.get("name") or "").strip()
        if not name:
            raise ValueError("参数或请求头名称不能为空")
        if len(name) > 120:
            raise ValueError("参数或请求头名称不能超过 120 个字符")
        identity = name.lower() if location == "header" else name
        if identity in seen:
            raise ValueError(f"参数或请求头名称重复：{name}")
        seen.add(identity)
        value_type = str(row.get("type") or "string").strip()
        if value_type not in ROW_TYPES:
            raise ValueError(f"不支持的参数类型：{value_type}")
        example = row.get("example")
        if example is None:
            example = ""
        elif not isinstance(example, str):
            example = json.dumps(example, ensure_ascii=False)
        if len(example) > 4096:
            raise ValueError("参数示例不能超过 4096 个字符")
        description = str(row.get("description") or "").strip()
        if len(description) > 512:
            raise ValueError("参数说明不能超过 512 个字符")
        normalized.append(
            {
                "enabled": bool(row.get("enabled", True)),
                "name": name,
                "type": value_type,
                "required": True if location == "path" else bool(row.get("required", False)),
                "example": example,
                "description": description,
            }
        )
    return normalized


def validate_path_parameters(path: str, rows: Iterable[Mapping[str, Any]]) -> None:
    expected = set(path_parameter_names(path))
    actual = {str(row.get("name") or "").strip() for row in rows}
    if expected == actual:
        return
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append(f"缺少：{', '.join(missing)}")
    if extra:
        details.append(f"多余：{', '.join(extra)}")
    raise ValueError(f"Path 参数与路径占位符不一致（{'；'.join(details)}）")


def parse_json_value(value: Any) -> Any | None:
    """Accept a JSON-compatible value or its JSON text form from the editor."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON 内容格式不合法") from exc
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("JSON 内容格式不合法") from exc
    return value
