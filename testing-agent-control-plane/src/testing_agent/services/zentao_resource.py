from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx


@dataclass(slots=True)
class ZentaoProjectResource:
    id: int
    name: str
    deleted: bool = False


def parse_zentao_remote_id(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        raise ValueError("禅道资源ID不能为空")
    try:
        remote_id = int(text)
    except ValueError as exc:
        raise ValueError("禅道资源ID必须为数字") from exc
    if remote_id <= 0:
        raise ValueError("禅道资源ID必须大于0")
    return remote_id


def truncate_error(message: str, limit: int = 500) -> str:
    text = str(message or "")
    return text if len(text) <= limit else text[:limit]


class ZentaoResourceClient:
    def __init__(self, service_base_url: str = "http://127.0.0.1:8010"):
        self.service_base_url = service_base_url.rstrip("/")

    async def get_project(self, connection: Any, remote_resource_id: str) -> ZentaoProjectResource:
        remote_id = parse_zentao_remote_id(remote_resource_id)
        data = await self._get(connection, f"api/v1/zentao/projects/{remote_id}")
        return ZentaoProjectResource(
            id=int(data.get("id") or remote_id),
            name=str(data.get("name") or ""),
            deleted=bool(data.get("deleted") or False),
        )

    async def list_projects(
        self,
        connection: Any,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        return await self._list(connection, "api/v1/zentao/projects", page, page_size)

    async def list_project_executions(
        self,
        connection: Any,
        remote_project_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        remote_id = parse_zentao_remote_id(remote_project_id)
        return await self._list(
            connection,
            f"api/v1/zentao/projects/{remote_id}/executions",
            page,
            page_size,
        )

    async def list_execution_testtasks(
        self,
        connection: Any,
        remote_execution_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        remote_id = parse_zentao_remote_id(remote_execution_id)
        return await self._list(
            connection,
            f"api/v1/zentao/executions/{remote_id}/testtasks",
            page,
            page_size,
        )

    async def list_execution_stories(
        self,
        connection: Any,
        remote_execution_id: str,
    ) -> dict[str, Any]:
        remote_id = parse_zentao_remote_id(remote_execution_id)
        return await self._list_without_paging(
            connection,
            f"api/v1/zentao/executions/{remote_id}/stories",
        )

    async def list_execution_cases(
        self,
        connection: Any,
        remote_execution_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        remote_id = parse_zentao_remote_id(remote_execution_id)
        return await self._list(
            connection,
            f"api/v1/zentao/executions/{remote_id}/cases",
            page,
            page_size,
        )

    async def list_execution_bugs(
        self,
        connection: Any,
        remote_execution_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        remote_id = parse_zentao_remote_id(remote_execution_id)
        return await self._list(
            connection,
            f"api/v1/zentao/executions/{remote_id}/bugs",
            page,
            page_size,
        )

    async def create_test_cases(
        self,
        connection: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        data = await self._request(
            connection,
            "api/v1/zentao/testcases",
            {},
            method="POST",
            json_body=body,
            timeout=60,
        )
        if not isinstance(data.get("items"), list):
            raise RuntimeError("禅道测试用例创建响应数据解析失败")
        return data

    async def _get(self, connection: Any, resource_path: str) -> dict[str, Any]:
        data = await self._request(connection, resource_path, {})
        if not isinstance(data, dict):
            raise RuntimeError("禅道资源数据解析失败")
        return data

    async def _list(
        self,
        connection: Any,
        resource_path: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return await self._request(
            connection,
            resource_path,
            {
                "page": str(max(page, 1)),
                "page_size": str(min(max(page_size, 1), 1000)),
            },
        )

    async def _list_without_paging(self, connection: Any, resource_path: str) -> dict[str, Any]:
        return await self._request(connection, resource_path, {})

    async def _request(
        self,
        connection: Any,
        resource_path: str,
        query: dict[str, str],
        *,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
        timeout: float = 10,
    ) -> dict[str, Any]:
        url = urljoin(self.service_base_url + "/", resource_path)
        token = str(getattr(connection, "access_token", "") or "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        params = {"base_url": getattr(connection, "base_url", "") or "", **query}
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"禅道资源查询失败，HTTP {response.status_code}: {response.text}")
        envelope = response.json()
        if int(envelope.get("code", 0)) != 0:
            raise RuntimeError(str(envelope.get("message") or "禅道资源查询失败"))
        data = envelope.get("data")
        if data is None:
            raise RuntimeError("禅道资源响应为空")
        if not isinstance(data, dict):
            raise RuntimeError("禅道资源数据解析失败")
        return data
