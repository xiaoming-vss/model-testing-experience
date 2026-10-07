import json

import httpx
import pytest

from testing_agent.services.mcp_client import McpCallError, McpClient


@pytest.mark.asyncio
async def test_streamable_client_preserves_session_and_parses_sse_and_text_results():
    methods = []

    def handler(request):
        p = json.loads(request.content)
        methods.append(p["method"])
        assert request.headers["token"] == "personal-token"
        if p["method"] == "initialize":
            data = {
                "jsonrpc": "2.0",
                "id": p["id"],
                "result": {
                    "capabilities": {"tools": {}},
                    "protocolVersion": "2025-03-26",
                },
            }
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "session-1", "Content-Type": "text/event-stream"},
                text=f"event: message\r\ndata: {json.dumps(data)}\r\n\r\n",
            )
        assert request.headers["Mcp-Session-Id"] == "session-1"
        assert request.headers["MCP-Protocol-Version"] == "2025-03-26"
        if p["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": p["id"],
                "result": {
                    "content": [
                        {"type": "text", "text": "HTTP 200"},
                        {"type": "text", "text": '{"status":"success","id":42}'},
                    ],
                },
            },
        )

    async with McpClient(
        "http://mcp.test/mcp", "personal-token", transport=httpx.MockTransport(handler)
    ) as client:
        assert (await client.call("post_bugs", {"payload": {}}, write=True))["id"] == 42
    assert methods == ["initialize", "notifications/initialized", "tools/call"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["mismatched-id", "invalid-json", "tool-error", "http-500"])
async def test_ambiguous_write_errors_preserve_uncertainty(failure):
    def handler(request):
        if failure == "http-500":
            return httpx.Response(500)
        if failure == "invalid-json":
            return httpx.Response(200, text="not JSON")
        p = json.loads(request.content)
        if failure == "tool-error":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": p["id"], "result": {"isError": True}}
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 999, "result": {}})

    client = McpClient(
        "http://mcp.test/mcp", "personal-token", transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(McpCallError) as error:
            await client.call("post_bugs", {}, write=True)
        assert error.value.uncertain
        assert "personal-token" not in str(error.value)
    finally:
        await client.http.aclose()
