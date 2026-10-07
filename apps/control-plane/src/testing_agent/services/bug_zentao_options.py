"""Read minimal Bug creation choices using the current actor's MCP connection."""

from typing import Any

from testing_agent.core.errors import AppError
from testing_agent.services.mcp_client import McpClient
from testing_agent.services.zentao_mcp import deleted, normalize_list

BUILD_TOOL = "get_executions_executionID_builds"
PAGE_SIZE = 100


async def read_pages(
    client: McpClient, tool: str, key: str, arguments: dict[str, Any]
) -> list[dict[str, Any]]:
    # Older bundled schemas silently omit build paging arguments upstream.
    # Do not present a truncated first page as the full selection list.
    if tool == BUILD_TOOL:
        catalog = await client._request("tools/list", {})
        definition: dict[str, Any] = next(
            (t for t in catalog.get("tools", []) if t.get("name") == tool), {}
        )
        properties = definition.get("inputSchema", {}).get("properties", {})
        if not {"executionID", "pageID", "recPerPage"}.issubset(properties):
            raise AppError(502, "请升级禅道 MCP：版本查询工具缺少分页参数", 502)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, 101):
        data = await client.call(tool, {**arguments, "pageID": page, "recPerPage": PAGE_SIZE})
        batch, total = normalize_list(data, key)
        page_ids = {item["id"] for item in batch}
        if seen.intersection(page_ids):
            raise AppError(502, "禅道分页返回重复数据，无法确认完整列表", 502)
        # Build APIs can emit two rows for a build's source and download paths.
        unique = {item["id"]: item for item in batch}
        seen.update(page_ids)
        items.extend(unique.values())
        if total is not None and len(seen) >= total:
            return items
        if total is None and len(unique) < PAGE_SIZE:
            return items
        if not batch:
            raise AppError(502, "禅道分页数据不完整", 502)
    raise AppError(502, "禅道候选项超过查询上限", 502)


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


async def validate_choices(client, target, product_id, request):
    if request.opened_build != ["trunk"]:
        allowed = {item["id"] for item in await build_options(client, target, product_id)}
        if not set(request.opened_build).issubset(allowed):
            raise AppError(400, "所选影响版本已删除或不属于当前禅道执行及产品，请重新选择", 400)
    if request.assigned_to:
        allowed = {item["account"] for item in await user_options(client)}
        if request.assigned_to not in allowed:
            raise AppError(400, "所选禅道指派人不存在或不可用，请重新选择", 400)
