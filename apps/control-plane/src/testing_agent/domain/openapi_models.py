"""Shared models, limits and reference resolution for OpenAPI import."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

from testing_agent.domain.api_interface import ALLOWED_METHODS

MAX_REF_DEPTH = 32
MAX_WARNINGS = 200
MEDIA_FORM_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")
ALLOWED_METHODS_LOWER = frozenset(method.lower() for method in ALLOWED_METHODS)
SOURCE_NAME_MAX = 255
SOURCE_VERSION_MAX = 64
DESCRIPTION_MAX = 1024
RESPONSE_DESCRIPTION_MAX = 512
BODY_TEXT_MAX = 20000


@dataclass(frozen=True, slots=True)
class ParsedEndpoint:
    method: str
    path: str
    name: str
    description: str
    tags: list[str]
    headers: list[dict[str, Any]]
    path_params: list[dict[str, Any]]
    query_params: list[dict[str, Any]]
    body_type: str
    body_schema: Any | None
    body_example: Any | None
    body_text: str
    response_status: int
    response_description: str
    response_schema: Any | None
    response_example: Any | None
    security: Any | None = None


@dataclass(slots=True)
class ParsedOpenApiDocument:
    source_name: str
    source_version: str
    base_path: str
    endpoints: list[ParsedEndpoint] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    security_schemes: dict[str, Any] = field(default_factory=dict)


class Resolver:
    def __init__(self, root: dict[str, Any], warnings: list[dict[str, str]]) -> None:
        self.root = root
        self.warnings = warnings

    def resolve(self, value: Any, *, depth: int = 0, seen: frozenset[str] = frozenset()) -> Any:
        if depth > MAX_REF_DEPTH:
            self.warn("ref_depth", "引用层级过深，已保留原引用", value)
            return value
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str):
                if not ref.startswith("#/"):
                    return value
                if ref in seen:
                    self.warn("ref_cycle", "检测到循环引用，已保留原引用", value)
                    return value
                target = self._pointer(ref)
                if target is None:
                    self.warn("ref_missing", f"未找到本地引用 {ref}", value)
                    return value
                return self.resolve(target, depth=depth + 1, seen=seen | {ref})
            return {
                key: self.resolve(item, depth=depth + 1, seen=seen) for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.resolve(item, depth=depth + 1, seen=seen) for item in value]
        return value

    def _pointer(self, ref: str) -> Any | None:
        current: Any = self.root
        for raw_part in ref[2:].split("/"):
            part = unquote(raw_part).replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                return None
        return current

    def warn(self, code: str, message: str, value: Any = None) -> None:
        warning = {"code": code, "message": message}
        if isinstance(value, dict):
            method = value.get("method")
            path = value.get("path")
            if isinstance(method, str):
                warning["method"] = method
            if isinstance(path, str):
                warning["path"] = path
        self.warnings.append(warning)


def warn(
    warnings: list[dict[str, str]],
    code: str,
    message: str,
    *,
    method: str = "",
    path: str = "",
) -> None:
    if len(warnings) >= MAX_WARNINGS:
        return
    warning = {"code": code, "message": message}
    if method:
        warning["method"] = method
    if path:
        warning["path"] = path
    warnings.append(warning)
