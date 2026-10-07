"""Read instance identity from MCP; never trust a platform-entered address."""

from urllib.parse import urlsplit

from testing_agent.core.errors import AppError
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.service_instance import normalize_instance_url


def parse_instance_info(data):
    try:
        if data.get("schemaVersion") != 1:
            raise ValueError()
        result = {}
        for key in ("instanceUrl", "apiBaseUrl"):
            value = data.get(key)
            if not isinstance(value, str) or not value or len(value) > 512:
                raise ValueError()
            url = urlsplit(value)
            if url.query or url.fragment or any(c.isspace() for c in value):
                raise ValueError()
            result[key] = normalize_instance_url(value)
        return result
    except (ValueError, TypeError, AppError) as exc:
        raise AppError(502, "MCP 返回的禅道实例信息无效，请检查 MCP 服务配置", 502) from exc


async def discover_instance(endpoint, token, *, client_factory=None):
    try:
        async with (client_factory or McpClient)(endpoint, token) as client:
            return parse_instance_info(await client.call("get_zentao_instance", {}))
    except McpCallError as exc:
        raise AppError(
            502, "无法从 MCP 读取禅道实例信息，请检查连接及 get_zentao_instance 工具", 502
        ) from exc
