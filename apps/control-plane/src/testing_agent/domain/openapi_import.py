"""Parse OpenAPI 3.x / Swagger 2.0 documents into interface definitions.

The module is pure: it never reads files, calls the network or touches the
database. Services provide the bounded parsed YAML/JSON object and persist the
result after applying their own permission and diff rules.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from testing_agent.domain.api_interface import (
    normalize_base_path,
    normalize_method,
    normalize_path,
    normalize_tags,
    path_parameter_names,
)
from testing_agent.domain.openapi_models import (
    ALLOWED_METHODS_LOWER,
    DESCRIPTION_MAX,
    SOURCE_NAME_MAX,
    SOURCE_VERSION_MAX,
    ParsedEndpoint,
    ParsedOpenApiDocument,
    Resolver,
    warn,
)
from testing_agent.domain.openapi_parameters import (
    ensure_content_type,
    merged_parameters,
    normalize_param_rows,
    openapi3_body,
    swagger2_body,
)
from testing_agent.domain.openapi_responses import response_definition

__all__ = ["ParsedEndpoint", "ParsedOpenApiDocument", "parse_openapi_document"]


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
    resolver = Resolver(document, warnings)
    raw_info = document.get("info")
    info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
    source_name = str(info.get("title") or "").strip() or fallback_name.strip()
    source_version = str(info.get("version") or "").strip()
    if len(source_name) > SOURCE_NAME_MAX:
        warn(warnings, "field_truncated", f"文档标题超过 {SOURCE_NAME_MAX} 个字符，已截断")
        source_name = source_name[:SOURCE_NAME_MAX]
    if len(source_version) > SOURCE_VERSION_MAX:
        warn(warnings, "field_truncated", f"文档版本超过 {SOURCE_VERSION_MAX} 个字符，已截断")
        source_version = source_version[:SOURCE_VERSION_MAX]
    base_path = _document_base_path(document, resolver, warnings)
    version = _document_version(document)
    raw_security_schemes = (
        (document.get("components") or {}).get("securitySchemes")
        if version == 3 and isinstance(document.get("components"), dict)
        else document.get("securityDefinitions")
    )
    security_schemes = resolver.resolve(raw_security_schemes)
    if not isinstance(security_schemes, dict):
        security_schemes = {}

    endpoints: list[ParsedEndpoint] = []
    seen: set[str] = set()
    for raw_path, raw_path_item in paths.items():
        if not isinstance(raw_path, str):
            warn(warnings, "path_invalid", "接口路径不是字符串")
            continue
        path_item = resolver.resolve(raw_path_item)
        if not isinstance(path_item, dict):
            warn(warnings, "path_item_invalid", f"路径 {raw_path} 的定义不是对象", path=raw_path)
            continue
        method_keys = [
            key
            for key in path_item
            if isinstance(key, str) and key.lower() in ALLOWED_METHODS_LOWER
        ]
        for method_key in method_keys:
            method = normalize_method(method_key)
            operation = path_item.get(method_key)
            if not isinstance(operation, dict):
                warn(
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
                warn(
                    warnings,
                    "operation_skipped",
                    f"{method} {raw_path} 已跳过：{exc}",
                    method=method,
                    path=raw_path,
                )
                continue
            key = f"{endpoint.method} {endpoint.path}"
            if key in seen:
                warn(
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
        security_schemes=security_schemes,
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
    resolver: Resolver,
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
        warn(warnings, "base_path_variable", "文档 base path 含变量，已忽略")
        return ""
    parsed = urlsplit(raw)
    path = parsed.path if parsed.scheme or parsed.netloc else raw
    if path in ("", "/"):
        return ""
    try:
        return normalize_base_path(path)
    except ValueError as exc:
        warn(warnings, "base_path_invalid", f"文档 base path 无法解析：{exc}")
        return ""


def _parse_operation(
    document: dict[str, Any],
    resolver: Resolver,
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
        warn(
            warnings,
            "deprecated",
            f"{method} {normalized_path} 在文档中标记为 deprecated，仍按启用导入",
            method=method,
            path=normalized_path,
        )
    parameters = merged_parameters(
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

    header_rows = normalize_param_rows(headers, "header", warnings, method, normalized_path)
    path_param_rows = normalize_param_rows(path_rows, "path", warnings, method, normalized_path)
    query_param_rows = normalize_param_rows(query_rows, "query", warnings, method, normalized_path)

    if version == 3:
        body = openapi3_body(
            resolver, warnings, operation.get("requestBody"), method, normalized_path
        )
    else:
        body = swagger2_body(resolver, warnings, operation, method, normalized_path)

    if body["body_type"] != "none":
        header_rows = ensure_content_type(header_rows, body["media_type"], body["body_type"])

    response = response_definition(
        resolver, warnings, operation.get("responses"), method, normalized_path, version
    )

    summary = str(operation.get("summary") or "").strip()
    operation_id = str(operation.get("operationId") or "").strip()
    name = (summary or operation_id or f"{method} {normalized_path}").strip()[:120]
    description = str(operation.get("description") or "").strip()
    if len(description) > DESCRIPTION_MAX:
        warn(
            warnings,
            "field_truncated",
            f"接口说明超过 {DESCRIPTION_MAX} 个字符，已截断",
            method=method,
            path=normalized_path,
        )
        description = description[:DESCRIPTION_MAX]
    try:
        raw_tags = operation.get("tags")
        tags = normalize_tags(raw_tags if isinstance(raw_tags, list) else [])
    except ValueError as exc:
        warn(warnings, "tags_invalid", f"标签已忽略：{exc}", method=method, path=normalized_path)
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
        security=(
            resolver.resolve(operation.get("security"))
            if "security" in operation
            else resolver.resolve(document.get("security"))
        ),
    )
