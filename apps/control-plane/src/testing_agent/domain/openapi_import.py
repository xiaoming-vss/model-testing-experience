"""Parse OpenAPI 3.x / Swagger 2.0 documents into interface definitions.

The module is pure: it never reads files, calls the network or touches the
database. Services provide the bounded parsed YAML/JSON object and persist the
result after applying their own permission and diff rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

from testing_agent.domain.api_interface import (
    ALLOWED_METHODS,
    normalize_base_path,
    normalize_method,
    normalize_path,
    normalize_rows,
    normalize_tags,
    path_parameter_names,
)

_MAX_REF_DEPTH = 32
_MAX_WARNINGS = 200
_MEDIA_FORM_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")
_ALLOWED_METHODS_LOWER = frozenset(method.lower() for method in ALLOWED_METHODS)
_SOURCE_NAME_MAX = 255
_SOURCE_VERSION_MAX = 64
_DESCRIPTION_MAX = 1024
_RESPONSE_DESCRIPTION_MAX = 512
_BODY_TEXT_MAX = 20000


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


@dataclass(slots=True)
class ParsedOpenApiDocument:
    source_name: str
    source_version: str
    base_path: str
    endpoints: list[ParsedEndpoint] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)


class _Resolver:
    def __init__(self, root: dict[str, Any], warnings: list[dict[str, str]]) -> None:
        self.root = root
        self.warnings = warnings

    def resolve(self, value: Any, *, depth: int = 0, seen: frozenset[str] = frozenset()) -> Any:
        if depth > _MAX_REF_DEPTH:
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


def parse_openapi_document(
    document: dict[str, Any],
    *,
    fallback_name: str = "",
) -> ParsedOpenApiDocument:
    if not isinstance(document, dict):
        raise ValueError("接口文档必须是对象")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("接口文档缺少 paths 对象")

    warnings: list[dict[str, str]] = []
    resolver = _Resolver(document, warnings)
    raw_info = document.get("info")
    info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
    source_name = str(info.get("title") or "").strip() or fallback_name.strip()
    source_version = str(info.get("version") or "").strip()
    if len(source_name) > _SOURCE_NAME_MAX:
        _warn(warnings, "field_truncated", f"文档标题超过 {_SOURCE_NAME_MAX} 个字符，已截断")
        source_name = source_name[:_SOURCE_NAME_MAX]
    if len(source_version) > _SOURCE_VERSION_MAX:
        _warn(warnings, "field_truncated", f"文档版本超过 {_SOURCE_VERSION_MAX} 个字符，已截断")
        source_version = source_version[:_SOURCE_VERSION_MAX]
    base_path = _document_base_path(document, resolver, warnings)
    version = _document_version(document)

    endpoints: list[ParsedEndpoint] = []
    seen: set[str] = set()
    for raw_path, raw_path_item in paths.items():
        if not isinstance(raw_path, str):
            _warn(warnings, "path_invalid", "接口路径不是字符串")
            continue
        path_item = resolver.resolve(raw_path_item)
        if not isinstance(path_item, dict):
            _warn(warnings, "path_item_invalid", f"路径 {raw_path} 的定义不是对象", path=raw_path)
            continue
        method_keys = [
            key
            for key in path_item
            if isinstance(key, str) and key.lower() in _ALLOWED_METHODS_LOWER
        ]
        for method_key in method_keys:
            method = normalize_method(method_key)
            operation = path_item.get(method_key)
            if not isinstance(operation, dict):
                _warn(
                    warnings,
                    "operation_invalid",
                    f"{method} {raw_path} 的定义不是对象",
                    method=method,
                    path=raw_path,
                )
                continue
            try:
                endpoint = _parse_operation(
                    document,
                    resolver,
                    warnings,
                    path=raw_path,
                    method=method,
                    operation=operation,
                    path_item=path_item,
                    version=version,
                )
            except ValueError as exc:
                _warn(
                    warnings,
                    "operation_skipped",
                    f"{method} {raw_path} 已跳过：{exc}",
                    method=method,
                    path=raw_path,
                )
                continue
            key = f"{endpoint.method} {endpoint.path}"
            if key in seen:
                _warn(
                    warnings,
                    "duplicate_identity",
                    f"{key} 在文档中重复，只保留第一个",
                    method=endpoint.method,
                    path=endpoint.path,
                )
                continue
            seen.add(key)
            endpoints.append(endpoint)

    endpoints.sort(key=lambda item: (item.path, item.method))
    return ParsedOpenApiDocument(
        source_name=source_name,
        source_version=source_version,
        base_path=base_path,
        endpoints=endpoints,
        warnings=warnings,
    )


def _document_version(document: dict[str, Any]) -> int:
    openapi = document.get("openapi")
    if isinstance(openapi, str) and openapi.strip().startswith("3."):
        return 3
    swagger = document.get("swagger")
    if isinstance(swagger, str) and swagger.strip() == "2.0":
        return 2
    raise ValueError("仅支持 OpenAPI 3.x 或 Swagger 2.0 文档")


def _document_base_path(
    document: dict[str, Any],
    resolver: _Resolver,
    warnings: list[dict[str, str]],
) -> str:
    raw = ""
    if _document_version(document) == 3:
        servers = resolver.resolve(document.get("servers"))
        if isinstance(servers, list):
            for server in servers:
                if not isinstance(server, dict):
                    continue
                url = server.get("url")
                if isinstance(url, str) and url.strip():
                    raw = url.strip()
                    break
    else:
        base_path = document.get("basePath")
        if isinstance(base_path, str):
            raw = base_path.strip()
    if not raw:
        return ""
    if "{" in raw or "}" in raw:
        _warn(warnings, "base_path_variable", "文档 base path 含变量，已忽略")
        return ""
    parsed = urlsplit(raw)
    path = parsed.path if parsed.scheme or parsed.netloc else raw
    if path in ("", "/"):
        return ""
    try:
        return normalize_base_path(path)
    except ValueError as exc:
        _warn(warnings, "base_path_invalid", f"文档 base path 无法解析：{exc}")
        return ""


def _parse_operation(
    document: dict[str, Any],
    resolver: _Resolver,
    warnings: list[dict[str, str]],
    *,
    path: str,
    method: str,
    operation: dict[str, Any],
    path_item: dict[str, Any],
    version: int,
) -> ParsedEndpoint:
    normalized_path = normalize_path(path)
    if operation.get("deprecated") is True:
        _warn(
            warnings,
            "deprecated",
            f"{method} {normalized_path} 在文档中标记为 deprecated，仍按启用导入",
            method=method,
            path=normalized_path,
        )
    if operation.get("security"):
        _warn(
            warnings,
            "security_not_imported",
            "安全方案未自动转换为 Authorization 请求头",
            method=method,
            path=normalized_path,
        )

    parameters = _merged_parameters(
        resolver,
        warnings,
        path_item.get("parameters"),
        operation.get("parameters"),
        method=method,
        path=normalized_path,
        version=version,
    )
    headers = [row for row in parameters if row["in"] == "header"]
    path_rows = [row for row in parameters if row["in"] == "path"]
    query_rows = [row for row in parameters if row["in"] == "query"]

    expected_path_names = path_parameter_names(normalized_path)
    path_rows = [row for row in path_rows if row["name"] in expected_path_names]
    for name in expected_path_names:
        if not any(row["name"] == name for row in path_rows):
            path_rows.append(
                {
                    "enabled": True,
                    "name": name,
                    "type": "string",
                    "required": True,
                    "example": "",
                    "description": "",
                }
            )

    header_rows = _normalize_param_rows(headers, "header", warnings, method, normalized_path)
    path_param_rows = _normalize_param_rows(path_rows, "path", warnings, method, normalized_path)
    query_param_rows = _normalize_param_rows(query_rows, "query", warnings, method, normalized_path)

    if version == 3:
        body = _openapi3_body(
            resolver, warnings, operation.get("requestBody"), method, normalized_path
        )
    else:
        body = _swagger2_body(resolver, warnings, operation, method, normalized_path)

    if body["body_type"] != "none":
        header_rows = _ensure_content_type(header_rows, body["media_type"], body["body_type"])

    response = _response_definition(
        resolver, warnings, operation.get("responses"), method, normalized_path, version
    )

    summary = str(operation.get("summary") or "").strip()
    operation_id = str(operation.get("operationId") or "").strip()
    name = (summary or operation_id or f"{method} {normalized_path}").strip()[:120]
    description = str(operation.get("description") or "").strip()
    if len(description) > _DESCRIPTION_MAX:
        _warn(
            warnings,
            "field_truncated",
            f"接口说明超过 {_DESCRIPTION_MAX} 个字符，已截断",
            method=method,
            path=normalized_path,
        )
        description = description[:_DESCRIPTION_MAX]
    try:
        raw_tags = operation.get("tags")
        tags = normalize_tags(raw_tags if isinstance(raw_tags, list) else [])
    except ValueError as exc:
        _warn(warnings, "tags_invalid", f"标签已忽略：{exc}", method=method, path=normalized_path)
        tags = []

    return ParsedEndpoint(
        method=method,
        path=normalized_path,
        name=name,
        description=description,
        tags=tags,
        headers=header_rows,
        path_params=path_param_rows,
        query_params=query_param_rows,
        body_type=body["body_type"],
        body_schema=body["body_schema"],
        body_example=body["body_example"],
        body_text=body["body_text"],
        response_status=response["status"],
        response_description=response["description"],
        response_schema=response["schema"],
        response_example=response["example"],
    )


def _merged_parameters(
    resolver: _Resolver,
    warnings: list[dict[str, str]],
    path_parameters: Any,
    operation_parameters: Any,
    *,
    method: str,
    path: str,
    version: int,
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for source in (path_parameters, operation_parameters):
        if source is None:
            continue
        if not isinstance(source, list):
            _warn(
                warnings,
                "parameters_invalid",
                "parameters 不是数组，已忽略",
                method=method,
                path=path,
            )
            continue
        for raw in source:
            parameter = resolver.resolve(raw)
            if not isinstance(parameter, dict) or "$ref" in parameter:
                _warn(
                    warnings,
                    "parameter_ref_unresolved",
                    "参数引用无法解析，已跳过",
                    method=method,
                    path=path,
                )
                continue
            location = str(parameter.get("in") or "").strip()
            name = str(parameter.get("name") or "").strip()
            if not name:
                continue
            if location == "cookie":
                _warn(
                    warnings,
                    "cookie_parameter_skipped",
                    f"Cookie 参数 {name} 不支持，已跳过",
                    method=method,
                    path=path,
                )
                continue
            if location not in {"path", "query", "header"}:
                continue
            schema = resolver.resolve(parameter.get("schema")) if version == 3 else {}
            if not isinstance(schema, dict):
                schema = {}
            value_type = _parameter_type(schema, parameter, version)
            example = _parameter_example(parameter, schema)
            merged[(location, name.lower() if location == "header" else name)] = {
                "in": location,
                "name": name,
                "type": value_type,
                "required": bool(parameter.get("required", location == "path")),
                "example": example,
                "description": str(parameter.get("description") or ""),
            }
    return list(merged.values())


def _parameter_type(schema: dict[str, Any], parameter: dict[str, Any], version: int) -> str:
    raw = schema.get("type") or (parameter.get("type") if version == 2 else None)
    value = str(raw or "string").strip().lower()
    aliases = {
        "int": "integer",
        "long": "integer",
        "float": "number",
        "double": "number",
        "bool": "boolean",
        "binary": "file",
        "byte": "string",
    }
    value = aliases.get(value, value)
    if value not in {"string", "integer", "number", "boolean", "array", "object", "file"}:
        return "string"
    return value


def _parameter_example(parameter: dict[str, Any], schema: dict[str, Any]) -> Any:
    example = parameter.get("example")
    if example is None:
        example = schema.get("example")
    if example is None:
        examples = parameter.get("examples")
        if isinstance(examples, dict):
            for item in examples.values():
                if isinstance(item, dict) and "value" in item:
                    example = item["value"]
                    break
    return example


def _normalize_param_rows(
    rows: list[dict[str, Any]],
    location: str,
    warnings: list[dict[str, str]],
    method: str,
    path: str,
) -> list[dict[str, Any]]:
    try:
        return normalize_rows(rows, location=location)  # type: ignore[arg-type]
    except ValueError as exc:
        _warn(
            warnings,
            "parameters_invalid",
            f"{location} 参数已忽略：{exc}",
            method=method,
            path=path,
        )
        return []


def _openapi3_body(
    resolver: _Resolver,
    warnings: list[dict[str, str]],
    raw_body: Any,
    method: str,
    path: str,
) -> dict[str, Any]:
    if raw_body is None:
        return _empty_body()
    body = resolver.resolve(raw_body)
    if not isinstance(body, dict) or "$ref" in body:
        _warn(warnings, "request_body_unresolved", "requestBody 无法解析", method=method, path=path)
        return _empty_body()
    content = body.get("content")
    if not isinstance(content, dict) or not content:
        return _empty_body()
    media_type, media = _choose_media(content)
    if media is None:
        return _empty_body()
    if not isinstance(media, dict):
        media = {}
    schema = resolver.resolve(media.get("schema"))
    example = _media_example(resolver, media)
    body_type = _body_type_for_media(media_type)
    body_text = ""
    if body_type == "raw" and example is not None:
        body_text = (
            example
            if isinstance(example, str)
            else json.dumps(example, ensure_ascii=False, indent=2)
        )
        if len(body_text) > _BODY_TEXT_MAX:
            _warn(
                warnings,
                "field_truncated",
                f"原始请求体超过 {_BODY_TEXT_MAX} 个字符，已截断",
                method=method,
                path=path,
            )
            body_text = body_text[:_BODY_TEXT_MAX]
    return {
        "body_type": body_type,
        "body_schema": schema,
        "body_example": example,
        "body_text": body_text,
        "media_type": media_type,
    }


def _swagger2_body(
    resolver: _Resolver,
    warnings: list[dict[str, str]],
    operation: dict[str, Any],
    method: str,
    path: str,
) -> dict[str, Any]:
    parameters = operation.get("parameters")
    if not isinstance(parameters, list):
        return _empty_body()
    body_param: dict[str, Any] | None = None
    form_params: list[dict[str, Any]] = []
    for raw in parameters:
        parameter = resolver.resolve(raw)
        if not isinstance(parameter, dict):
            continue
        if parameter.get("in") == "body":
            body_param = parameter
        elif parameter.get("in") == "formData":
            form_params.append(parameter)
    consumes = operation.get("consumes")
    media_types = [str(item) for item in consumes] if isinstance(consumes, list) else []
    media_type = _swagger_media_type(media_types, form=bool(form_params))
    if body_param is not None:
        body_schema_value = resolver.resolve(body_param.get("schema"))
        body_type = "form" if media_type in _MEDIA_FORM_TYPES else "json"
        return {
            "body_type": body_type,
            "body_schema": body_schema_value,
            "body_example": None,
            "body_text": "",
            "media_type": media_type,
        }
    if form_params:
        properties: dict[str, Any] = {}
        required: list[str] = []
        example: dict[str, Any] = {}
        for parameter in form_params:
            name = str(parameter.get("name") or "").strip()
            if not name:
                continue
            schema: dict[str, Any] = {
                "type": _parameter_type(parameter, parameter, 2),
            }
            properties[name] = schema
            if parameter.get("required"):
                required.append(name)
            value = parameter.get("example")
            if value is None:
                value = schema.get("example")
            if value is not None:
                example[name] = value
        body_schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            body_schema["required"] = required
        return {
            "body_type": "form",
            "body_schema": body_schema,
            "body_example": example or None,
            "body_text": "",
            "media_type": media_type,
        }
    return _empty_body()


def _empty_body() -> dict[str, Any]:
    return {
        "body_type": "none",
        "body_schema": None,
        "body_example": None,
        "body_text": "",
        "media_type": "",
    }


def _body_type_for_media(media_type: str) -> str:
    lowered = media_type.lower()
    if "json" in lowered:
        return "json"
    if lowered in _MEDIA_FORM_TYPES:
        return "form"
    return "raw"


def _swagger_media_type(media_types: list[str], *, form: bool) -> str:
    if form:
        for media_type in media_types:
            if media_type.lower() in _MEDIA_FORM_TYPES:
                return media_type
        return "application/x-www-form-urlencoded"
    if media_types:
        return media_types[0]
    return "application/json"


def _choose_media(content: dict[str, Any]) -> tuple[str, Any]:
    items = [(str(key), value) for key, value in content.items()]
    for key, value in items:
        if "json" in key.lower():
            return key, value
    for key, value in items:
        if key.lower() in _MEDIA_FORM_TYPES:
            return key, value
    return items[0] if items else ("", None)


def _media_example(resolver: _Resolver, media: dict[str, Any]) -> Any:
    if "example" in media:
        return media.get("example")
    examples = media.get("examples")
    if isinstance(examples, dict):
        for item in examples.values():
            resolved = resolver.resolve(item)
            if isinstance(resolved, dict) and "value" in resolved:
                return resolved["value"]
    return None


def _ensure_content_type(
    rows: list[dict[str, Any]], media_type: str, body_type: str
) -> list[dict[str, Any]]:
    if any(str(row.get("name") or "").lower() == "content-type" for row in rows):
        return rows
    value = media_type
    if not value:
        value = {
            "json": "application/json",
            "form": "application/x-www-form-urlencoded",
            "raw": "text/plain",
        }.get(body_type, "")
    if not value:
        return rows
    return [
        *rows,
        {
            "enabled": True,
            "name": "Content-Type",
            "type": "string",
            "required": False,
            "example": value,
            "description": "请求体类型",
        },
    ]


def _response_definition(
    resolver: _Resolver,
    warnings: list[dict[str, str]],
    raw_responses: Any,
    method: str,
    path: str,
    version: int,
) -> dict[str, Any]:
    if not isinstance(raw_responses, dict):
        return {
            "status": 200,
            "description": "",
            "schema": None,
            "example": None,
        }
    status_key = _choose_response_key(raw_responses)
    if status_key is None:
        return {
            "status": 200,
            "description": "",
            "schema": None,
            "example": None,
        }
    response = resolver.resolve(raw_responses[status_key])
    if not isinstance(response, dict) or "$ref" in response:
        _warn(
            warnings,
            "response_unresolved",
            f"响应 {status_key} 无法解析",
            method=method,
            path=path,
        )
        return {
            "status": 200,
            "description": "",
            "schema": None,
            "example": None,
        }
    status = 200 if status_key in {"default", "2XX"} else int(status_key)
    description = str(response.get("description") or "")
    if len(description) > _RESPONSE_DESCRIPTION_MAX:
        _warn(
            warnings,
            "field_truncated",
            f"响应说明超过 {_RESPONSE_DESCRIPTION_MAX} 个字符，已截断",
            method=method,
            path=path,
        )
        description = description[:_RESPONSE_DESCRIPTION_MAX]
    if version == 3:
        content = response.get("content")
        media_type, media = _choose_media(content) if isinstance(content, dict) else ("", None)
        if isinstance(media, dict):
            schema = resolver.resolve(media.get("schema"))
            example = _media_example(resolver, media)
        else:
            schema = None
            example = None
    else:
        schema = resolver.resolve(response.get("schema"))
        example = None
        examples = response.get("examples")
        if isinstance(examples, dict):
            for value in examples.values():
                example = value
                break
    return {
        "status": status,
        "description": description,
        "schema": schema,
        "example": example,
    }


def _choose_response_key(responses: dict[str, Any]) -> str | None:
    success: list[tuple[int, str]] = []
    for key in responses:
        if not isinstance(key, str):
            continue
        if key.isdigit() and 200 <= int(key) <= 299:
            success.append((int(key), key))
    if success:
        return min(success)[1]
    if "2XX" in responses:
        return "2XX"
    if "default" in responses:
        return "default"
    return None


def _warn(
    warnings: list[dict[str, str]],
    code: str,
    message: str,
    *,
    method: str = "",
    path: str = "",
) -> None:
    if len(warnings) >= _MAX_WARNINGS:
        return
    warning = {"code": code, "message": message}
    if method:
        warning["method"] = method
    if path:
        warning["path"] = path
    warnings.append(warning)
