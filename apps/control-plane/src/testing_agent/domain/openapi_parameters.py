"""Parameter, body and media normalization for OpenAPI import."""

from __future__ import annotations

import json
from typing import Any

from testing_agent.domain.api_interface import normalize_rows
from testing_agent.domain.openapi_example import generate_example
from testing_agent.domain.openapi_models import (
    BODY_TEXT_MAX,
    MEDIA_FORM_TYPES,
    Resolver,
    warn,
)


def merged_parameters(
    resolver: Resolver,
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
            warn(
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
                warn(
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
                warn(
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


def normalize_param_rows(
    rows: list[dict[str, Any]],
    location: str,
    warnings: list[dict[str, str]],
    method: str,
    path: str,
) -> list[dict[str, Any]]:
    try:
        return normalize_rows(rows, location=location)  # type: ignore[arg-type]
    except ValueError as exc:
        warn(
            warnings,
            "parameters_invalid",
            f"{location} 参数已忽略：{exc}",
            method=method,
            path=path,
        )
        return []


def openapi3_body(
    resolver: Resolver,
    warnings: list[dict[str, str]],
    raw_body: Any,
    method: str,
    path: str,
) -> dict[str, Any]:
    if raw_body is None:
        return _empty_body()
    body = resolver.resolve(raw_body)
    if not isinstance(body, dict) or "$ref" in body:
        warn(warnings, "request_body_unresolved", "requestBody 无法解析", method=method, path=path)
        return _empty_body()
    content = body.get("content")
    if not isinstance(content, dict) or not content:
        return _empty_body()
    media_type, media = choose_media(content)
    if media is None:
        return _empty_body()
    if not isinstance(media, dict):
        media = {}
    schema = resolver.resolve(media.get("schema"))
    body_type = _body_type_for_media(media_type)
    example = _body_example(body_type, schema, media_example(resolver, media))
    body_text = ""
    if body_type == "raw" and example is not None:
        body_text = (
            example
            if isinstance(example, str)
            else json.dumps(example, ensure_ascii=False, indent=2)
        )
        if len(body_text) > BODY_TEXT_MAX:
            warn(
                warnings,
                "field_truncated",
                f"原始请求体超过 {BODY_TEXT_MAX} 个字符，已截断",
                method=method,
                path=path,
            )
            body_text = body_text[:BODY_TEXT_MAX]
    return {
        "body_type": body_type,
        "body_schema": schema,
        "body_example": example,
        "body_text": body_text,
        "media_type": media_type,
    }


def swagger2_body(
    resolver: Resolver,
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
        body_type = "form" if media_type in MEDIA_FORM_TYPES else "json"
        return {
            "body_type": body_type,
            "body_schema": body_schema_value,
            "body_example": _body_example(body_type, body_schema_value, body_param.get("example")),
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
            "body_example": _body_example("form", body_schema, example or None),
            "body_text": "",
            "media_type": media_type,
        }
    return _empty_body()


def _body_example(body_type: str, schema: Any, example: Any) -> Any:
    """Keeps the documented example; structured bodies without one get a derived placeholder."""
    if example is not None or body_type not in {"json", "form"}:
        return example
    return generate_example(schema)


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
    if lowered in MEDIA_FORM_TYPES:
        return "form"
    return "raw"


def _swagger_media_type(media_types: list[str], *, form: bool) -> str:
    if form:
        for media_type in media_types:
            if media_type.lower() in MEDIA_FORM_TYPES:
                return media_type
        return "application/x-www-form-urlencoded"
    if media_types:
        return media_types[0]
    return "application/json"


def choose_media(content: dict[str, Any]) -> tuple[str, Any]:
    items = [(str(key), value) for key, value in content.items()]
    for key, value in items:
        if "json" in key.lower():
            return key, value
    for key, value in items:
        if key.lower() in MEDIA_FORM_TYPES:
            return key, value
    return items[0] if items else ("", None)


def media_example(resolver: Resolver, media: dict[str, Any]) -> Any:
    if "example" in media:
        return media.get("example")
    examples = media.get("examples")
    if isinstance(examples, dict):
        for item in examples.values():
            resolved = resolver.resolve(item)
            if isinstance(resolved, dict) and "value" in resolved:
                return resolved["value"]
    return None


def ensure_content_type(
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
