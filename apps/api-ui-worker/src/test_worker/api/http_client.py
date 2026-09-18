"""HTTP client wrapper for API worker execution."""

from __future__ import annotations

from typing import Any

import httpx


async def execute_request(request: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout_ms / 1000 if timeout_ms > 0 else 30) as client:
        response = await client.request(
            request["method"],
            request["url"],
            headers=request.get("headers") or {},
            params=request.get("query") or {},
            json=request.get("json") if "json" in request else None,
            data=request.get("data") if "data" in request else None,
            content=request.get("content") if "content" in request else None,
        )
    return {
        "statusCode": response.status_code,
        "headersJson": _headers_json(response),
        "body": response.text,
    }


def _headers_json(response: httpx.Response) -> str:
    import json

    return json.dumps(dict(response.headers), ensure_ascii=False, separators=(",", ":"))
