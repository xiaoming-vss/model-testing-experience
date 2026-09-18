from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from testing_agent.services.gitlab_auth import normalize_gitlab_base_url
from testing_agent.services.zentao_resource import truncate_error

GITLAB_PAGE_SIZE_LIMIT = 100


class GitLabResourceError(RuntimeError):
    """GitLab 资源调用失败;status_code 为 0 表示请求未发出或响应不可用。"""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


def canonical_resource_id(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise GitLabResourceError("GitLab 资源缺少规范数字 ID")
    if not str(value).isascii() or not str(value).isdigit() or int(value) <= 0:
        raise GitLabResourceError("GitLab 资源缺少规范数字 ID")
    return str(int(value))


def encode_gitlab_id(resource_id: str) -> str:
    """GitLab 项目/群组 id 支持数字 id 与 URL 编码 path(如 group/sub)。"""
    text = str(resource_id or "").strip()
    if not text:
        raise GitLabResourceError("GitLab 资源ID不能为空")
    return quote(text, safe="")


def group_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name") or "",
        "fullPath": item.get("full_path") or "",
        "parentId": item.get("parent_id"),
        "description": item.get("description") or "",
        "webUrl": item.get("web_url") or "",
    }


def repository_payload(item: dict[str, Any]) -> dict[str, Any]:
    namespace = item.get("namespace") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name") or "",
        "path": item.get("path") or "",
        "pathWithNamespace": item.get("path_with_namespace") or "",
        "namespaceFullPath": (namespace.get("full_path") if isinstance(namespace, dict) else "")
        or "",
        "defaultBranch": item.get("default_branch") or "",
        "description": item.get("description") or "",
        "webUrl": item.get("web_url") or "",
    }


def branch_payload(item: dict[str, Any]) -> dict[str, Any]:
    commit = item.get("commit") or {}
    return {
        "name": item.get("name") or "",
        "isDefault": bool(item.get("default")),
        "isProtected": bool(item.get("protected")),
        "commitId": (commit.get("id") if isinstance(commit, dict) else "") or "",
        "commitTitle": (commit.get("title") if isinstance(commit, dict) else "") or "",
    }


def response_total(headers: httpx.Headers, item_count: int) -> int:
    raw = headers.get("X-Total")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            pass
    return item_count


def diff_line_stats(diff_text: str) -> tuple[int, int]:
    """unified diff 文本的增删行数(跳过 +++/--- 文件头行)。"""
    additions = 0
    deletions = 0
    for line in str(diff_text or "").splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def compare_payload(item: dict[str, Any]) -> dict[str, Any]:
    """compare API 响应 → 概览统计:commits 数与增删行数(工单 08)。"""
    commits = item.get("commits")
    commits_count = len(commits) if isinstance(commits, list) else 0
    diffs = item.get("diffs")
    diff_list = diffs if isinstance(diffs, list) else []
    additions = 0
    deletions = 0
    for diff in diff_list:
        if not isinstance(diff, dict):
            continue
        part_additions, part_deletions = diff_line_stats(str(diff.get("diff") or ""))
        additions += part_additions
        deletions += part_deletions
    return {
        "commitsCount": commits_count,
        "additions": additions,
        "deletions": deletions,
    }


class GitLabResourceClient:
    """直连 GitLab API v4 的资源客户端(手写 httpx,沿用 gitlab_auth 风格)。

    仅供资源代理端点(级联下拉)使用;凭据由调用方从个人 GitLab 集成
    连接解密后传入。GitLab 侧失败统一抛 GitLabResourceError,由服务层
    映射为 3401 系列错误码。
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def get_group(self, base_url: str, access_token: str, group_id: str) -> dict[str, Any]:
        group, _ = await self._request_json(
            base_url,
            access_token,
            f"/api/v4/groups/{encode_gitlab_id(group_id)}",
            {"with_projects": "false"},
        )
        if not isinstance(group, dict):
            raise GitLabResourceError("GitLab 群组信息格式不合法")
        return {**group_payload(group), "id": canonical_resource_id(group.get("id"))}

    async def get_repository_group_scope(
        self, base_url: str, access_token: str, group_id: str, repository_id: str
    ) -> dict[str, Any]:
        """Check namespace ownership, not projects merely shared with a group.

        GitLab Projects/Groups APIs expose namespace.full_path and full_path.
        A slash boundary distinguishes a descendant from a similarly named group.
        """
        group, _ = await self._request_json(
            base_url,
            access_token,
            f"/api/v4/groups/{encode_gitlab_id(group_id)}",
            {"with_projects": "false"},
        )
        repository, _ = await self._request_json(
            base_url, access_token, f"/api/v4/projects/{encode_gitlab_id(repository_id)}", {}
        )
        if not isinstance(group, dict) or not isinstance(repository, dict):
            raise GitLabResourceError("GitLab 响应数据格式不合法")
        namespace = repository.get("namespace")
        if not isinstance(namespace, dict):
            raise GitLabResourceError("GitLab 仓库归属信息缺失")
        parent = group.get("full_path")
        child = namespace.get("full_path")
        within = (
            isinstance(parent, str)
            and bool(parent)
            and isinstance(child, str)
            and bool(child)
            and namespace.get("kind") == "group"
            and (child == parent or child.startswith(parent + "/"))
        )
        return {"withinGroup": within, "repositoryId": canonical_resource_id(repository.get("id"))}

    async def list_groups(
        self,
        base_url: str,
        access_token: str,
        *,
        search: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        params = {
            "top_level_only": "false",
            "order_by": "name",
            "sort": "asc",
            "page": str(max(page, 1)),
            "per_page": str(min(max(page_size, 1), GITLAB_PAGE_SIZE_LIMIT)),
        }
        if search:
            params["search"] = str(search)
        data, headers = await self._request(base_url, access_token, "/api/v4/groups", params)
        return {
            "items": [group_payload(item) for item in data],
            "total": response_total(headers, len(data)),
        }

    async def list_group_repositories(
        self,
        base_url: str,
        access_token: str,
        group_id: str,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        encoded_group_id = encode_gitlab_id(group_id)
        params = {
            "include_subgroups": "true",
            "with_shared": "false",
            "page": str(max(page, 1)),
            "per_page": str(min(max(page_size, 1), GITLAB_PAGE_SIZE_LIMIT)),
        }
        data, headers = await self._request(
            base_url,
            access_token,
            f"/api/v4/groups/{encoded_group_id}/projects",
            params,
        )
        return {
            "items": [repository_payload(item) for item in data],
            "total": response_total(headers, len(data)),
        }

    async def list_repository_branches(
        self,
        base_url: str,
        access_token: str,
        repository_id: str,
        *,
        search: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        encoded_repository_id = encode_gitlab_id(repository_id)
        params = {
            "page": str(max(page, 1)),
            "per_page": str(min(max(page_size, 1), GITLAB_PAGE_SIZE_LIMIT)),
        }
        if search:
            params["search"] = str(search)
        data, headers = await self._request(
            base_url,
            access_token,
            f"/api/v4/projects/{encoded_repository_id}/repository/branches",
            params,
        )
        return {
            "items": [branch_payload(item) for item in data],
            "total": response_total(headers, len(data)),
        }

    async def compare_repository_branches(
        self,
        base_url: str,
        access_token: str,
        repository_id: str,
        from_ref: str,
        to_ref: str,
    ) -> dict[str, Any]:
        """GitLab compare API:from 到 to 的 commits 数与增删行数。

        from_ref 可为 git 空树 SHA(工单 08 无基线仓库口径)。任一 ref 不存在
        时 GitLab 返回 404,抛 GitLabResourceError 由服务层映射为仓库级错误。
        """
        encoded_repository_id = encode_gitlab_id(repository_id)
        params = {"from": str(from_ref), "to": str(to_ref)}
        data, _ = await self._request_json(
            base_url,
            access_token,
            f"/api/v4/projects/{encoded_repository_id}/repository/compare",
            params,
        )
        if not isinstance(data, dict):
            raise GitLabResourceError("GitLab 响应数据格式不合法")
        return compare_payload(data)

    async def _request(
        self,
        base_url: str,
        access_token: str,
        resource_path: str,
        params: dict[str, str],
    ) -> tuple[list[dict[str, Any]], httpx.Headers]:
        data, headers = await self._request_json(base_url, access_token, resource_path, params)
        if not isinstance(data, list):
            raise GitLabResourceError("GitLab 响应数据格式不合法")
        return data, headers

    async def _request_json(
        self,
        base_url: str,
        access_token: str,
        resource_path: str,
        params: dict[str, str],
    ) -> tuple[Any, httpx.Headers]:
        try:
            normalized_base_url = normalize_gitlab_base_url(base_url)
        except ValueError as exc:
            raise GitLabResourceError(f"GitLab 地址不合法: {truncate_error(str(exc))}") from exc
        url = f"{normalized_base_url}{resource_path}"
        headers = {"PRIVATE-TOKEN": access_token}
        try:
            async with httpx.AsyncClient(timeout=30.0, transport=self._transport) as client:
                response = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise GitLabResourceError(f"GitLab 请求失败: {truncate_error(str(exc))}") from exc
        if response.status_code < 200 or response.status_code >= 300:
            detail = truncate_error(response.text)
            raise GitLabResourceError(
                f"GitLab 资源查询失败，HTTP {response.status_code}: {detail}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise GitLabResourceError("GitLab 响应解析失败") from exc
        return data, response.headers
