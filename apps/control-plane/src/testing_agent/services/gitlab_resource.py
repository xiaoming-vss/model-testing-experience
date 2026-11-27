from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from testing_agent.services.connection_security import (
    require_secure_scheme,
    warn_if_insecure,
)
from testing_agent.services.gitlab_auth import normalize_gitlab_base_url

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


def normalize_clone_url(clone_url: str) -> str:
    """校验仓库克隆地址：只允许 HTTP(S)，且不能内嵌凭据、查询参数或片段。"""
    normalized = str(clone_url or "").strip()
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GitLabResourceError("GitLab 仓库克隆地址不合法")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GitLabResourceError("GitLab 仓库克隆地址不能包含凭据、查询参数或片段")
    return normalized.rstrip("/")


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


class GitLabResourceClient:
    """直连 GitLab API v4 的资源客户端(手写 httpx,沿用 gitlab_auth 风格)。

    仅供资源代理端点(级联下拉)使用;凭据由调用方从个人 GitLab 集成
    连接解密后传入。GitLab 侧失败统一抛 GitLabResourceError,由服务层
    映射为 3401 系列错误码。
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def get_project(
        self,
        base_url: str,
        access_token: str,
        repository_id: str,
        *,
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
    ) -> dict[str, Any]:
        """读取仓库元信息，供代码分析固定克隆地址和默认分支。"""
        project, _ = await self._request_json(
            base_url,
            access_token,
            f"/api/v4/projects/{encode_gitlab_id(repository_id)}",
            {},
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        if not isinstance(project, dict):
            raise GitLabResourceError("GitLab 仓库信息格式不合法")
        clone_url = project.get("http_url_to_repo")
        if not isinstance(clone_url, str) or not clone_url.strip():
            raise GitLabResourceError("GitLab 仓库缺少克隆地址")
        return {
            "id": canonical_resource_id(project.get("id")),
            "pathWithNamespace": str(project.get("path_with_namespace") or ""),
            "cloneUrl": normalize_clone_url(clone_url),
            "defaultBranch": str(project.get("default_branch") or ""),
        }

    async def get_branch(
        self,
        base_url: str,
        access_token: str,
        repository_id: str,
        branch: str,
        *,
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
    ) -> dict[str, Any]:
        """读取单个分支，用于绑定前校验分支存在且当前操作人可访问。"""
        encoded_branch = encode_gitlab_id(branch)
        data, _ = await self._request_json(
            base_url,
            access_token,
            f"/api/v4/projects/{encode_gitlab_id(repository_id)}/repository/branches/{encoded_branch}",
            {},
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        if not isinstance(data, dict):
            raise GitLabResourceError("GitLab 分支信息格式不合法")
        name = str(data.get("name") or "")
        commit = data.get("commit")
        commit_id = str(commit.get("id") or "") if isinstance(commit, dict) else ""
        if not name or not commit_id:
            raise GitLabResourceError("GitLab 分支信息缺少名称或提交")
        return {"name": name, "commitId": commit_id}

    async def resolve_commit(
        self,
        base_url: str,
        access_token: str,
        repository_id: str,
        ref: str,
        *,
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
    ) -> str:
        """把分支/tag/SHA 解析为固定 commit SHA。"""
        data, _ = await self._request(
            base_url,
            access_token,
            f"/api/v4/projects/{encode_gitlab_id(repository_id)}/repository/commits",
            {"ref_name": str(ref), "per_page": "1"},
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        if not data or not isinstance(data[0], dict) or not data[0].get("id"):
            raise GitLabResourceError(f"GitLab ref {ref} 无法解析为 commit")
        return str(data[0]["id"])

    async def get_repository_group_scope(
        self,
        base_url: str,
        access_token: str,
        group_id: str,
        repository_id: str,
        *,
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
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
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        repository, _ = await self._request_json(
            base_url,
            access_token,
            f"/api/v4/projects/{encode_gitlab_id(repository_id)}",
            {},
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
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
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
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
        data, headers = await self._request(
            base_url,
            access_token,
            "/api/v4/groups",
            params,
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
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
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
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
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
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
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
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
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        return {
            "items": [branch_payload(item) for item in data],
            "total": response_total(headers, len(data)),
        }

    async def _request(
        self,
        base_url: str,
        access_token: str,
        resource_path: str,
        params: dict[str, str],
        *,
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
    ) -> tuple[list[dict[str, Any]], httpx.Headers]:
        data, headers = await self._request_json(
            base_url,
            access_token,
            resource_path,
            params,
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        if not isinstance(data, list):
            raise GitLabResourceError("GitLab 响应数据格式不合法")
        return data, headers

    async def _request_json(
        self,
        base_url: str,
        access_token: str,
        resource_path: str,
        params: dict[str, str],
        *,
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
    ) -> tuple[Any, httpx.Headers]:
        try:
            normalized_base_url = normalize_gitlab_base_url(base_url)
            require_secure_scheme(normalized_base_url, allow_http=allow_http)
        except ValueError as exc:
            raise GitLabResourceError(f"GitLab 地址不合法: {exc}") from exc
        warn_if_insecure(
            "gitlab",
            normalized_base_url,
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        url = f"{normalized_base_url}{resource_path}"
        headers = {"PRIVATE-TOKEN": access_token}
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                transport=self._transport,
                verify=not insecure_skip_verify,
            ) as client:
                response = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            # httpx messages can carry the request line; the class name is enough.
            raise GitLabResourceError(
                f"GitLab 请求失败: {type(exc).__name__}", status_code=0
            ) from exc
        if response.status_code < 200 or response.status_code >= 300:
            # GitLab's response body may echo request data; report the status only.
            raise GitLabResourceError(
                f"GitLab 资源查询失败，HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise GitLabResourceError("GitLab 响应解析失败") from exc
        return data, response.headers
