"""Response normalization for OpenAPI import."""

from __future__ import annotations

from typing import Any

from testing_agent.domain.openapi_example import generate_example
from testing_agent.domain.openapi_models import (
    RESPONSE_DESCRIPTION_MAX,
    Resolver,
    warn,
)
from testing_agent.domain.openapi_parameters import choose_media, media_example


def response_definition(
    resolver: Resolver,
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
        warn(
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
    if len(description) > RESPONSE_DESCRIPTION_MAX:
        warn(
            warnings,
            "field_truncated",
            f"响应说明超过 {RESPONSE_DESCRIPTION_MAX} 个字符，已截断",
            method=method,
            path=path,
        )
        description = description[:RESPONSE_DESCRIPTION_MAX]
    if version == 3:
        content = response.get("content")
        media_type, media = choose_media(content) if isinstance(content, dict) else ("", None)
        if isinstance(media, dict):
            schema = resolver.resolve(media.get("schema"))
            example = media_example(resolver, media)
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
    # Keeps the documented example; a structured response without one gets a derived placeholder.
    if example is None:
        example = generate_example(schema)
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
