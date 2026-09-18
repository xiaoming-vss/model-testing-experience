from unittest.mock import patch

import httpx
import pytest

from app.core.exceptions import ERR_ZENTAO_INVALID_RESPONSE, ERR_ZENTAO_REQUEST, AppError
from app.core.http_client import HttpClientConfig, HttpJsonClient


@pytest.mark.anyio
@pytest.mark.parametrize("body", ["<html>Error</html>", "", "[]", "null", '"text"', "42"])
async def test_invalid_upstream_body_returns_integration_error(body: str) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    upstream = httpx.AsyncClient(
        transport=transport, base_url="https://zentao.example.com/api.php/v2"
    )
    with patch("app.core.http_client.httpx.AsyncClient", return_value=upstream):
        client = HttpJsonClient(HttpClientConfig(base_url=str(upstream.base_url)))
        with pytest.raises(AppError) as caught:
            await client.request_json("GET", "/projects", "Project query")
    assert caught.value.error_code == ERR_ZENTAO_INVALID_RESPONSE
    assert caught.value.error_code.http_status == 502


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [200, 503])
async def test_json_success_and_http_failure_keep_existing_behavior(status_code: int) -> None:
    payload = {"status": "success", "projects": []}
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json=payload))
    upstream = httpx.AsyncClient(
        transport=transport, base_url="https://zentao.example.com/api.php/v2"
    )
    with patch("app.core.http_client.httpx.AsyncClient", return_value=upstream):
        client = HttpJsonClient(HttpClientConfig(base_url=str(upstream.base_url)))
        if status_code == 200:
            assert await client.request_json("GET", "/projects", "Project query") == payload
        else:
            with pytest.raises(AppError) as caught:
                await client.request_json("GET", "/projects", "Project query")
            assert caught.value.error_code == ERR_ZENTAO_REQUEST
