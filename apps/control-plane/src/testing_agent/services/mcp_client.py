"""Streamable HTTP client for explicit, program-controlled MCP tool calls."""

import json
from typing import Any

import httpx


class McpCallError(Exception):
    def __init__(self, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


class McpClient:
    def __init__(self, url: str, token: str, *, transport=None, timeout: float = 30):
        self.http = httpx.AsyncClient(
            headers={"token": token, "Accept": "application/json, text/event-stream"},
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )
        self.url = url
        self.request_id = 0

    async def __aenter__(self):
        try:
            result = await self._request(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "mtx-control-plane", "version": "0.1.0"},
                },
            )
            if not result.get("capabilities", {}).get("tools") and (
                "tools" not in result.get("capabilities", {})
            ):
                raise McpCallError("MCP 服务未提供工具调用能力")
            protocol = result.get("protocolVersion")
            if not isinstance(protocol, str):
                raise McpCallError("MCP 初始化结果缺少协议版本")
            self.http.headers["MCP-Protocol-Version"] = protocol
            await self._request("notifications/initialized", {}, notification=True)
            return self
        except BaseException:
            await self.http.aclose()
            raise

    async def __aexit__(self, *args):
        await self.http.aclose()

    async def list_tools(self) -> dict[str, Any]:
        """Read the negotiated server's tool catalog without exposing raw RPC dispatch."""
        return await self._request("tools/list", {})

    async def _request(self, method, params, *, write=False, notification=False):
        self.request_id += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = self.request_id
        try:
            response = await self.http.post(self.url, json=payload)
        except httpx.HTTPError as exc:
            # Do not include request headers, credentials or remote error bodies.
            raise McpCallError("MCP 请求超时或连接失败", uncertain=write) from exc
        if response.status_code >= 400:
            raise McpCallError(
                f"MCP 请求失败（HTTP {response.status_code}）",
                uncertain=write and response.status_code >= 500,
            )
        if response.headers.get("Mcp-Session-Id"):
            self.http.headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
        if notification and response.status_code in (200, 202, 204):
            return {}
        try:
            if "text/event-stream" in response.headers.get("content-type", ""):
                messages = []
                for event in response.text.replace("\r\n", "\n").split("\n\n"):
                    data = "\n".join(
                        line[5:].lstrip() for line in event.splitlines() if line.startswith("data:")
                    )
                    if data:
                        messages.append(json.loads(data))
                body = next(m for m in messages if m.get("id") == payload["id"])
            else:
                body = response.json()
            if body.get("jsonrpc") != "2.0" or body.get("id") != payload["id"]:
                raise ValueError()
            if "error" in body:
                # Invalid method/arguments are rejected before tool execution.
                code = (body.get("error") or {}).get("code")
                raise McpCallError(
                    "MCP 工具调用失败", uncertain=write and code not in (-32600, -32601, -32602)
                )
            result = body["result"]
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, KeyError, StopIteration, AttributeError, TypeError) as exc:
            raise McpCallError("MCP 返回格式异常", uncertain=write) from exc

    async def call(
        self, name: str, arguments: dict, *, write: bool = False, timeout: float | None = None
    ) -> dict:
        original_timeout = self.http.timeout
        try:
            if timeout is not None:
                self.http.timeout = httpx.Timeout(timeout)
            result = await self._request(
                "tools/call", {"name": name, "arguments": arguments}, write=write
            )
        finally:
            self.http.timeout = original_timeout
        if result.get("isError"):
            raise McpCallError("MCP 工具执行失败", uncertain=write)
        data = result.get("structuredContent")
        http_status = None
        for content in result.get("content", []):
            if content.get("type") != "text":
                continue
            value = content.get("text", "")
            if value.startswith("HTTP "):
                try:
                    http_status = int(value[5:])
                except ValueError:
                    raise McpCallError("MCP 上游状态格式异常", uncertain=write) from None
            else:
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict) and data is None:
                        data = parsed
                except (ValueError, TypeError):
                    pass
        if http_status is not None and not 200 <= http_status < 300:
            raise McpCallError(
                f"禅道操作失败（HTTP {http_status}）",
                uncertain=write and http_status >= 500,
            )
        if not isinstance(data, dict):
            raise McpCallError("禅道返回数据无法解析", uncertain=write)
        if "status" in data and data["status"] != "success":
            if name == "upload_bug_attachment":
                # Dedicated tool distinguishes pre-upload failures from uncertain writes.
                raise McpCallError(
                    {
                        "invalid_file_or_source": "附件大小、名称或 S3 来源不符合 MCP 上传配置",
                        "source_unavailable": "MCP 无法读取 S3 附件，请检查网络和下载票据",
                        "file_integrity_failed": "附件大小或摘要校验失败",
                        "bug_access_denied": "无法访问原禅道 Bug，请检查本人权限",
                        "upload_rejected": "禅道拒绝附件，请检查格式、上传限制和本人权限",
                        "temporary_storage_unavailable": "MCP 临时磁盘不可用",
                    }.get(
                        str(data.get("errorCode") or ""),
                        "附件上传未成功，请检查 MCP 上传配置、网络和本人权限",
                    ),
                    uncertain=write and data.get("uncertain") is not False,
                )
            raise McpCallError("禅道返回业务失败结果", uncertain=write)
        return data
