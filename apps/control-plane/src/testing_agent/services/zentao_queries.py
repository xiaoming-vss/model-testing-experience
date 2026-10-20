"""Zentao resource candidates, retaining provider pagination and token refresh behavior."""

from typing import Any

from testing_agent.core.errors import ErrZentaoRemoteResourceUnavailable, dynamic_error
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.services.integration_access import ActivePersonalConnection, EnsureZentaoToken
from testing_agent.services.zentao_resource import truncate_error


class ZentaoResources:
    def __init__(
        self,
        *,
        authorize: ActivePersonalConnection,
        ensure_token: EnsureZentaoToken,
        client: Any | None,
    ) -> None:
        self.authorize = authorize
        self.ensure_token = ensure_token
        self.client = client

    async def list_projects(
        self,
        connection_id: str,
        user_id: str,
        *,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        connection = await self.authorize(user_id, "zentao", connection_id, project_id)
        if self.client is None:
            raise ErrZentaoRemoteResourceUnavailable()
        result = await self._call(
            self.client.list_projects,
            connection,
            page,
            page_size,
        )
        items = [
            {
                "id": item_value(item, "id"),
                "name": item_value(item, "name"),
                "code": item_value(item, "code", default=""),
                "description": item_value(item, "description", default=""),
                "status": item_value(item, "status", default=""),
                "begin": item_value(item, "begin", default=""),
                "end": item_value(item, "end", default=""),
                "createdAt": item_value(item, "created_at", "createdAt", default=""),
                "updatedAt": item_value(item, "updated_at", "updatedAt", default=""),
            }
            for item in visible_zentao_items(result)
        ]
        return zentao_list_payload(connection_id, items, result)

    async def list_project_executions(
        self,
        connection_id: str,
        remote_project_id: str,
        user_id: str,
        *,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        connection = await self.authorize(user_id, "zentao", connection_id, project_id)
        if self.client is None:
            raise ErrZentaoRemoteResourceUnavailable()
        result = await self._call(
            self.client.list_project_executions,
            connection,
            remote_project_id,
            page,
            page_size,
        )
        items = []
        for item in visible_zentao_items(result):
            data = {
                "id": item_value(item, "id"),
                "projectId": item_value(item, "project_id", "projectId", default=0),
                "name": item_value(item, "name"),
                "description": item_value(item, "description", default=""),
                "status": item_value(item, "status", default=""),
                "begin": item_value(item, "begin", default=""),
                "end": item_value(item, "end", default=""),
                "createdAt": item_value(item, "created_at", "createdAt", default=""),
                "updatedAt": item_value(item, "updated_at", "updatedAt", default=""),
            }
            parent_id = item_value(item, "parent_id", "parentId", default=0)
            if parent_id:
                data["parentId"] = parent_id
            items.append(data)
        return zentao_list_payload(
            connection_id,
            items,
            result,
            remoteProjectId=remote_project_id,
        )

    async def list_execution_testtasks(
        self,
        connection_id: str,
        remote_execution_id: str,
        user_id: str,
        *,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        connection = await self.authorize(user_id, "zentao", connection_id, project_id)
        if self.client is None:
            raise ErrZentaoRemoteResourceUnavailable()
        result = await self._call(
            self.client.list_execution_testtasks,
            connection,
            remote_execution_id,
            page,
            page_size,
        )
        items = [
            {
                "id": item_value(item, "id"),
                "projectId": item_value(item, "project_id", "projectId", default=0),
                "executionId": item_value(item, "execution_id", "executionId", default=0),
                "name": item_value(item, "name"),
                "title": item_value(item, "title", default=""),
                "description": item_value(item, "description", default=""),
                "status": item_value(item, "status", default=""),
                "type": item_value(item, "type", default=""),
                "owner": item_value(item, "owner", default=""),
                "openedBy": item_value(item, "opened_by", "openedBy", default=""),
                "begin": item_value(item, "begin", default=""),
                "end": item_value(item, "end", default=""),
                "createdAt": item_value(item, "created_at", "createdAt", default=""),
                "updatedAt": item_value(item, "updated_at", "updatedAt", default=""),
            }
            for item in visible_zentao_items(result)
        ]
        return zentao_list_payload(
            connection_id,
            items,
            result,
            remoteExecutionId=remote_execution_id,
        )

    async def list_execution_stories(
        self,
        connection_id: str,
        remote_execution_id: str,
        user_id: str,
        project_id: str = "",
    ) -> dict:
        connection = await self.authorize(user_id, "zentao", connection_id, project_id)
        if self.client is None:
            raise ErrZentaoRemoteResourceUnavailable()
        result = await self._call(
            self.client.list_execution_stories,
            connection,
            remote_execution_id,
        )
        items = [
            {
                "id": item_value(item, "id"),
                "title": item_value(item, "title"),
                "productId": item_value(item, "product_id", "productId", default=0),
                "moduleId": item_value(item, "module_id", "moduleId", default=0),
                "planId": item_value(item, "plan_id", "planId", default=0),
                "status": item_value(item, "status", default=""),
                "stage": item_value(item, "stage", default=""),
                "priority": item_value(item, "priority", default=""),
                "assignedTo": item_value(item, "assigned_to", "assignedTo", default=""),
                "openedBy": item_value(item, "opened_by", "openedBy", default=""),
                "createdAt": item_value(item, "created_at", "createdAt", default=""),
                "updatedAt": item_value(item, "updated_at", "updatedAt", default=""),
            }
            for item in visible_zentao_items(result)
        ]
        return zentao_list_payload(
            connection_id,
            items,
            result,
            remoteExecutionId=remote_execution_id,
        )

    async def list_execution_cases(
        self,
        connection_id: str,
        remote_execution_id: str,
        user_id: str,
        *,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        connection = await self.authorize(user_id, "zentao", connection_id, project_id)
        if self.client is None:
            raise ErrZentaoRemoteResourceUnavailable()
        result = await self._call(
            self.client.list_execution_cases,
            connection,
            remote_execution_id,
            page,
            page_size,
        )
        items = [
            {
                "id": item_value(item, "id"),
                "module": item_value(item, "module", default=""),
                "title": item_value(item, "title"),
                "preconditions": item_value(item, "preconditions", default=""),
                "steps": item_value(item, "steps", default=""),
                "expectedResults": item_value(
                    item,
                    "expected_results",
                    "expectedResults",
                    default="",
                ),
                "priority": item_value(item, "priority", default=""),
                "caseType": item_value(item, "case_type", "caseType", default=""),
                "orderNo": item_value(item, "order_no", "orderNo", default=0),
            }
            for item in visible_zentao_items(result)
        ]
        return zentao_list_payload(
            connection_id,
            items,
            result,
            remoteExecutionId=remote_execution_id,
        )

    async def _call(self, method: Any, *args: Any) -> dict[str, Any]:
        if self.client is None:
            raise ErrZentaoRemoteResourceUnavailable()
        if args and isinstance(args[0], IntegrationConnection):
            await self.ensure_token(args[0])
        try:
            return await method(*args)
        except Exception as exc:
            raise dynamic_error(
                ErrZentaoRemoteResourceUnavailable,
                truncate_error(str(exc)),
            ) from exc


def item_value(item: Any, *names: str, default: Any = "") -> Any:
    for name in names:
        if isinstance(item, dict) and name in item:
            return item[name]
        if hasattr(item, name):
            return getattr(item, name)
    return default


def visible_zentao_items(result: dict[str, Any]) -> list[Any]:
    return [
        item
        for item in result.get("items", [])
        if not bool(item_value(item, "deleted", default=False))
    ]


def zentao_candidate_total(remote_total: int, visible_count: int) -> int:
    return visible_count if remote_total < visible_count else remote_total


def zentao_list_payload(
    connection_id: str,
    items: list[dict[str, Any]],
    result: dict[str, Any],
    **extra: str,
) -> dict[str, Any]:
    return {
        "connectionId": connection_id,
        **extra,
        "items": items,
        "total": zentao_candidate_total(int(result.get("total") or 0), len(items)),
    }
