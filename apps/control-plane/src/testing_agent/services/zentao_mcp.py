"""Project-scoped Zentao access and normalized binding candidates over MCP."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from testing_agent.core.errors import AppError, ErrBadRequest
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.personal_credentials import has_mcp_token
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
        if not has_mcp_token(own):
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


async def read_all_pages(
    fetch: Callable[[int], Awaitable[dict[str, Any]]],
    normalize: Callable[[dict[str, Any]], tuple[list[dict[str, Any]], int | None]],
    *,
    page_size: int = 100,
    max_pages: int = 100,
    paginated: bool = True,
    duplicate_message: str = "禅道分页返回重复数据，无法确认完整列表",
    incomplete_message: str = "禅道分页数据不完整",
    limit_message: str = "禅道资源超过查询上限，请缩小范围",
    error: Callable[[str], Exception] = lambda message: AppError(502, message, 502),
    deduplicate_page: bool = False,
) -> list[dict[str, Any]]:
    """Read every page with one duplicate/truncation policy."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        batch, total = normalize(await fetch(page))
        batch_ids = [item["id"] for item in batch]
        if seen.intersection(batch_ids):
            raise error(duplicate_message)
        unique = {item["id"]: item for item in batch}
        seen.update(batch_ids)
        items.extend(unique.values() if deduplicate_page else batch)
        if not paginated:
            return items
        if total is not None and len(seen) >= total:
            return items
        if total is None and len(batch) < page_size:
            return items
        if not batch:
            raise error(incomplete_message)
    raise error(limit_message)


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

        async def fetch(page: int) -> dict[str, Any]:
            paging = (
                {}
                if kind == "stories"
                else {"browseType": "all", "pageID": page, "recPerPage": 100}
            )
            return await client.call(name, {**arguments, **paging})

        try:
            async with McpClient(connection.endpoint, connection.token) as client:
                items = await read_all_pages(
                    fetch,
                    lambda data: normalize_list(data, kind),
                    paginated=kind != "stories",
                    duplicate_message="禅道分页返回重复资源，无法确认完整列表",
                    incomplete_message="禅道分页数据不完整",
                    limit_message="禅道资源超过查询上限，请缩小绑定范围",
                )
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

    async def list_all_project_executions(self, connection, remote_project_id):
        return await self.read(connection, "executions", remote_project_id)

    async def list_execution_stories(self, connection, remote_execution_id):
        return await self.read(connection, "stories", remote_execution_id)


class ZentaoMcpCandidateQuery:
    """Resolve the caller's MCP access and return binding candidates."""

    def __init__(self, connections) -> None:
        self.connections = connections

    async def list(
        self,
        *,
        user_id: str,
        project_id: str,
        kind: str,
        parent_id: str,
        mcp_service_id: str,
    ) -> dict[str, Any]:
        if kind != "projects" and not parent_id:
            raise ErrBadRequest()
        access = await ZentaoMcpAccess(self.connections).resolve(
            user_id, project_id, mcp_service_id=mcp_service_id
        )
        result = await ZentaoMcpResources().read(access, kind, parent_id)
        items = [item for item in result["items"] if not item["deleted"]]
        return {"items": items, "total": len(items)}
