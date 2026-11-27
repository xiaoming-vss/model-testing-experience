"""Read minimal Bug creation choices using the current actor's MCP connection."""

from typing import Any

from testing_agent.core.errors import AppError
from testing_agent.services.mcp_client import McpClient
from testing_agent.services.zentao_mcp import deleted, normalize_list, read_all_pages

BUILD_TOOL = "get_executions_executionID_builds"
PAGE_SIZE = 100


async def read_pages(
    client: McpClient, tool: str, key: str, arguments: dict[str, Any]
) -> list[dict[str, Any]]:
    # Older bundled schemas silently omit build paging arguments upstream.
    # Do not present a truncated first page as the full selection list.
    if tool == BUILD_TOOL:
        catalog = await client.list_tools()
        definition: dict[str, Any] = next(
            (t for t in catalog.get("tools", []) if t.get("name") == tool), {}
        )
        properties = definition.get("inputSchema", {}).get("properties", {})
        if not {"executionID", "pageID", "recPerPage"}.issubset(properties):
            raise AppError(502, "请升级禅道 MCP：版本查询工具缺少分页参数", 502)

    async def fetch(page: int) -> dict[str, Any]:
        return await client.call(tool, {**arguments, "pageID": page, "recPerPage": PAGE_SIZE})

    return await read_all_pages(
        fetch,
        lambda data: normalize_list(data, key),
        page_size=PAGE_SIZE,
        deduplicate_page=True,
        duplicate_message="禅道分页返回重复数据，无法确认完整列表",
        incomplete_message="禅道分页数据不完整",
        limit_message="禅道候选项超过查询上限",
    )


async def build_options(client, target, product_id):
    builds = await read_pages(client, BUILD_TOOL, "builds", {"executionID": target["execution"]})
    return [{"id": "trunk", "name": "主干 trunk"}] + [
        {"id": item["id"], "name": item["name"]}
        for item in builds
        if not item["deleted"]
        and str(item.get("product")) == str(product_id)
        and str(item.get("execution")) == str(target["execution"])
        and str(item.get("project")) == str(target["project"])
    ]


async def user_options(client):
    users = await read_pages(client, "get_users", "users", {"browseType": "inside"})
    options = {}
    for item in users:
        account = item.get("account")
        if (
            item["deleted"]
            or deleted(item.get("disabled"))
            or item.get("type", "inside") != "inside"
            or not isinstance(account, str)
            or not account
            or account in {"guest", "closed"}
            or len(account) > 100
            or any(c.isspace() or ord(c) < 32 for c in account)
        ):
            continue
        options[account] = {"account": account, "name": str(item.get("realname") or account)}
    return sorted(options.values(), key=lambda item: (item["name"], item["account"]))
