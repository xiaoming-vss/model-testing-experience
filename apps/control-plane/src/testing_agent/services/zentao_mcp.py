"""Project-scoped Zentao access and normalized binding candidates over MCP."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from testing_agent.core.errors import AppError
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.service_instance import instance_key
from testing_agent.services.shared_service import SharedServiceService
from testing_agent.services.zentao_mcp_identity import validate_identity
from testing_agent.services.zentao_mcp_instance import discover_instance
from testing_agent.services.zentao_mcp_selection import select_mcp_service


@dataclass
class ZentaoMcpConnection:
    connection_id: str
    base_url: str  # Zentao instance identity, not the MCP endpoint.
    endpoint: str
    token: str = field(repr=False)
    resources: dict = field(default_factory=dict, repr=False)
    service_id: str = ""


class ZentaoMcpAccess:
    def __init__(self, connections):
        self.catalog = SharedServiceService(connections)

    async def resolve(self, user_id, project_id, expected_instance="", mcp_service_id=""):
        await self.catalog.project(user_id, project_id)
        service = await select_mcp_service(
            self.catalog.session, project_id, mcp_service_id, expected_instance
        )
        own = await self.catalog.own_connection(service, user_id)
        if own is None or own.status != "active" or not (own.secret_json or {}).get("token"):
            raise AppError(400, "请在基础服务的禅道 MCP 中配置本人的 Token", 400)
        token = self.catalog.connections.credentials.mcp_token(
            own, user_id=user_id, project_id=project_id
        )
        info = await discover_instance(service.base_url, token, client_factory=McpClient)
        await validate_identity(self.catalog.session, service, info)
        if expected_instance and instance_key(expected_instance) != instance_key(
            info["instanceUrl"]
        ):
            raise AppError(400, "MCP 实际连接的禅道实例与已有绑定不一致", 400)
        return ZentaoMcpConnection(
            own.connection_id,
            info["instanceUrl"],
            service.base_url,
            token,
            service_id=service.service_id,
        )


def deleted(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_list(data: dict[str, Any], key: str) -> tuple[list[dict[str, Any]], int | None]:
    raw = data.get(key)
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise AppError(502, "禅道资源列表格式异常", 502)
    items = []
    for item in raw:
        try:
            identifier = int(item["id"])
            if identifier <= 0:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise AppError(502, "禅道资源编号异常", 502) from None
        items.append(
            {
                **item,
                "id": str(identifier),
                "name": str(item.get("name") or item.get("title") or identifier),
                "deleted": deleted(item.get("deleted")),
            }
        )
    total = data.get("total", data.get("count"))
    if total is None and isinstance(data.get("pager"), dict):
        total = data["pager"].get("recTotal")
    try:
        total = None if total is None else int(total)
        if total is not None and total < 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise AppError(502, "禅道分页总数异常", 502) from None
    return items, total


class ZentaoMcpResources:
    async def read(
        self, connection: ZentaoMcpConnection, kind: str, parent: str = ""
    ) -> dict[str, Any]:
        cache_key = (kind, parent)
        if cache_key in connection.resources:
            return connection.resources[cache_key]
        tools = {
            "projects": ("get_projects", {}),
            "executions": ("get_projects_projectID_executions", {"projectID": parent}),
            "stories": ("get_executions_executionID_stories", {"executionID": parent}),
        }
        name, arguments = tools[kind]
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            async with McpClient(connection.endpoint, connection.token) as client:
                for page in range(1, 101):
                    paging = (
                        {}
                        if kind == "stories"
                        else {"browseType": "all", "pageID": page, "recPerPage": 100}
                    )
                    data = await client.call(name, {**arguments, **paging})
                    batch, total = normalize_list(data, kind)
                    if any(item["id"] in seen for item in batch):
                        raise AppError(502, "禅道分页返回重复资源，无法确认完整列表", 502)
                    seen.update(item["id"] for item in batch)
                    items.extend(batch)
                    if (
                        kind == "stories"
                        or (total is not None and len(items) >= total)
                        or (total is None and len(batch) < 100)
                    ):
                        break
                    if not batch:
                        raise AppError(502, "禅道分页数据不完整", 502)
                else:
                    raise AppError(502, "禅道资源超过查询上限，请缩小绑定范围", 502)
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc
        result = {"items": items, "total": len(items)}
        connection.resources[cache_key] = result
        return result

    async def get_project(self, connection, remote_resource_id):
        # Current MCP has no project detail tool: verify against all accessible pages.
        result = await self.read(connection, "projects")
        for item in result["items"]:
            if item["id"] == str(int(remote_resource_id)):
                return SimpleNamespace(
                    id=int(item["id"]), name=item["name"], deleted=item["deleted"]
                )
        raise AppError(400, "禅道项目不存在或本人无权访问", 400)

    async def list_project_executions(self, connection, remote_project_id, page=1, page_size=100):
        result = await self.read(connection, "executions", remote_project_id)
        return {**result, "items": result["items"][(page - 1) * page_size : page * page_size]}

    async def list_execution_stories(self, connection, remote_execution_id):
        return await self.read(connection, "stories", remote_execution_id)
