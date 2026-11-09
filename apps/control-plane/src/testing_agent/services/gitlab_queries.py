"""GitLab resource queries over an explicitly authorized personal connection."""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from urllib.parse import urlsplit

from testing_agent.core.errors import (
    AppError,
    ErrGitLabRemoteResourceUnavailable,
    ErrIntegrationConnectionAuthFailed,
    ErrResourceBindingInvalid,
    dynamic_error,
)
from testing_agent.services.gitlab_resource import GitLabResourceClient, GitLabResourceError
from testing_agent.services.integration_access import ActivePersonalConnection
from testing_agent.services.personal_credentials import PersonalCredentialAccess
from testing_agent.services.zentao_resource import truncate_error

T = TypeVar("T")


class GitLabResources:
    def __init__(
        self,
        *,
        authorize: ActivePersonalConnection,
        credentials: PersonalCredentialAccess,
        client: GitLabResourceClient,
    ) -> None:
        self.authorize = authorize
        self.credentials = credentials
        self.client = client

    async def resolve_group_id(
        self, connection_id: str, project_id: str, group_id: str, *, user_id: str
    ) -> str:
        connection = await self.authorize(user_id, "gitlab", connection_id, project_id)
        group = await self._call(
            self.client.get_group,
            connection.base_url,
            self.credentials.gitlab_token(connection, user_id=user_id, project_id=project_id),
            group_id,
        )
        return str(group["id"])

    async def ensure_repository_scope(
        self,
        connection_id: str,
        project_id: str,
        group_id: str,
        repository_id: str,
        *,
        user_id: str,
    ) -> str:
        connection = await self.authorize(user_id, "gitlab", connection_id, project_id)
        result = await self._call(
            self.client.get_repository_group_scope,
            connection.base_url,
            self.credentials.gitlab_token(connection, user_id=user_id, project_id=project_id),
            group_id,
            repository_id,
        )
        if not result["withinGroup"]:
            raise dynamic_error(ErrResourceBindingInvalid, "仓库不在项目已绑群组范围内")
        return str(result["repositoryId"])

    async def get_project(
        self,
        connection_id: str,
        project_id: str,
        repository_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        connection = await self.authorize(user_id, "gitlab", connection_id, project_id)
        result = await self._call(
            self.client.get_project,
            connection.base_url,
            self.credentials.gitlab_token(connection, user_id=user_id, project_id=project_id),
            repository_id,
        )
        base = urlsplit(connection.base_url)
        clone = urlsplit(str(result.get("cloneUrl") or ""))
        if (
            clone.scheme.lower() != base.scheme.lower()
            or clone.netloc.lower() != base.netloc.lower()
        ):
            raise dynamic_error(ErrResourceBindingInvalid, "仓库克隆地址与 GitLab 服务地址不一致")
        return result

    async def get_branch(
        self,
        connection_id: str,
        project_id: str,
        repository_id: str,
        branch: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        connection = await self.authorize(user_id, "gitlab", connection_id, project_id)
        return await self._call(
            self.client.get_branch,
            connection.base_url,
            self.credentials.gitlab_token(connection, user_id=user_id, project_id=project_id),
            repository_id,
            branch,
        )

    async def resolve_commit(
        self,
        connection_id: str,
        project_id: str,
        repository_id: str,
        ref: str,
        *,
        user_id: str,
    ) -> str:
        connection = await self.authorize(user_id, "gitlab", connection_id, project_id)
        return await self._call(
            self.client.resolve_commit,
            connection.base_url,
            self.credentials.gitlab_token(connection, user_id=user_id, project_id=project_id),
            repository_id,
            ref,
        )

    async def list_groups(
        self,
        connection_id: str,
        *,
        user_id: str,
        project_id: str = "",
        search: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        """列出 PAT 可见群组(含子群组,搜索+分页),供级联下拉使用。"""
        connection = await self.authorize(user_id, "gitlab", connection_id, project_id)
        result = await self._call(
            self.client.list_groups,
            connection.base_url,
            self.credentials.gitlab_token(connection, user_id=user_id, project_id=project_id),
            search=search,
            page=page,
            page_size=page_size,
        )
        return {"connectionId": connection_id, **result}

    async def list_group_repositories(
        self,
        connection_id: str,
        group_id: str,
        *,
        user_id: str,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        """列出群组内仓库(覆盖子群组仓库,分页),供级联下拉使用。"""
        connection = await self.authorize(user_id, "gitlab", connection_id, project_id)
        result = await self._call(
            self.client.list_group_repositories,
            connection.base_url,
            self.credentials.gitlab_token(connection, user_id=user_id, project_id=project_id),
            group_id,
            page=page,
            page_size=page_size,
        )
        return {"connectionId": connection_id, "groupId": group_id, **result}

    async def list_repository_branches(
        self,
        connection_id: str,
        repository_id: str,
        *,
        user_id: str,
        project_id: str = "",
        search: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        """列出仓库分支(搜索+分页),供级联下拉使用。"""
        connection = await self.authorize(user_id, "gitlab", connection_id, project_id)
        result = await self._call(
            self.client.list_repository_branches,
            connection.base_url,
            self.credentials.gitlab_token(connection, user_id=user_id, project_id=project_id),
            repository_id,
            search=search,
            page=page,
            page_size=page_size,
        )
        return {"connectionId": connection_id, "repositoryId": repository_id, **result}

    async def _call(self, method: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        try:
            return await method(*args, **kwargs)
        except GitLabResourceError as exc:
            raise self._error(exc) from exc

    def _error(self, exc: GitLabResourceError) -> AppError:
        # PAT 失效(HTTP 401)归入鉴权失败;其余 GitLab 异常(404/5xx/网络等)统一映射。
        if exc.status_code == 401:
            return dynamic_error(
                ErrIntegrationConnectionAuthFailed,
                truncate_error(str(exc)),
            )
        return dynamic_error(
            ErrGitLabRemoteResourceUnavailable,
            truncate_error(str(exc)),
        )
