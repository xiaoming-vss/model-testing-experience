from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from testing_agent.core.enums import ConnectionStatus
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrIntegrationConnectionAuthFailed,
    dynamic_error,
)
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.services.connection_security import connection_security_flags
from testing_agent.services.integration_connections.common import ConnectionSupport
from testing_agent.services.zentao_resource import truncate_error


class GitLabConnectionCommands(ConnectionSupport):
    """GitLab credential, authentication and resource-query commands."""

    async def _create_gitlab(
        self,
        *,
        connection_id: str,
        body: dict[str, Any],
        user_id: str,
        project_id: str,
        commit: bool,
    ) -> dict:
        name = str(body.get("name") or "").strip()
        allow_http, insecure_skip_verify = self._security_flags(body)
        base_url = self._normalize_gitlab_base_url(str(body.get("baseUrl") or ""))
        self._require_secure_scheme(base_url, allow_http)
        access_token = str(body.get("accessToken") or "").strip()
        if not name or not access_token:
            raise ErrBadRequest()
        if commit:
            # Do not hold the read transaction opened by the access check
            # while waiting for the external authentication service.
            await self.repository.session.commit()
        await self._validate_gitlab(
            base_url,
            access_token,
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        await self.ensure_project_access(user_id, project_id)
        return await self._store_new(
            connection_id=connection_id,
            project_id=project_id,
            user_id=user_id,
            provider="gitlab",
            name=name,
            base_url=base_url,
            auth_type="personal_access_token",
            account="",
            secret_json={},
            access_token=self._encrypt_gitlab_token(access_token),
            status=ConnectionStatus.ACTIVE.value,
            last_auth_at=datetime.now(UTC),
            last_auth_error="",
            extra_json={
                "allowHttp": allow_http,
                "insecureSkipVerify": insecure_skip_verify,
            },
            commit=commit,
        )

    async def _update_gitlab(
        self,
        connection: IntegrationConnection,
        connection_id: str,
        body: dict[str, Any],
        user_id: str,
        project_id: str,
        *,
        commit: bool,
    ) -> dict:
        name = str(body.get("name", connection.name)).strip()
        if not name:
            raise ErrBadRequest()
        old_allow, old_insecure = connection_security_flags(connection.extra_json)
        allow_http, insecure_skip_verify = self._updated_security_flags(connection, body)
        base_url = self._normalize_gitlab_base_url(str(body.get("baseUrl", connection.base_url)))
        self._require_secure_scheme(base_url, allow_http)
        flags_changed = (allow_http, insecure_skip_verify) != (old_allow, old_insecure)
        credentials_changed = "baseUrl" in body or "accessToken" in body or flags_changed
        if "accessToken" in body:
            access_token = str(body["accessToken"] or "").strip()
            if not access_token:
                raise ErrBadRequest()
        else:
            access_token = self._decrypt_gitlab_token(connection.access_token)
        if credentials_changed:
            expected_updated_at = connection.updated_at
            # End the read transaction before waiting on the external service.
            if commit:
                await self.repository.commit()
            await self._validate_gitlab(
                base_url,
                access_token,
                allow_http=allow_http,
                insecure_skip_verify=insecure_skip_verify,
            )
            connection = await self._reload_locked(
                user_id,
                "gitlab",
                connection_id,
                project_id,
                expected_updated_at=expected_updated_at,
            )
        connection.name = name
        connection.base_url = base_url
        extra = dict(connection.extra_json or {})
        extra["allowHttp"] = allow_http
        extra["insecureSkipVerify"] = insecure_skip_verify
        connection.extra_json = extra
        if "accessToken" in body:
            connection.access_token = self._encrypt_gitlab_token(access_token)
        if credentials_changed:
            connection.status = ConnectionStatus.ACTIVE.value
            connection.last_auth_at = datetime.now(UTC)
            connection.last_auth_error = ""
        return await self._finish_write(connection, commit=commit)

    async def _validate_gitlab(
        self,
        base_url: str,
        access_token: str,
        *,
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
    ) -> None:
        try:
            await self.gitlab_auth_provider.validate(
                base_url,
                access_token,
                allow_http=allow_http,
                insecure_skip_verify=insecure_skip_verify,
            )
        except Exception as exc:
            raise dynamic_error(
                ErrIntegrationConnectionAuthFailed,
                truncate_error(str(exc)),
            ) from exc

    async def ensure_gitlab_repository_scope(
        self,
        connection_id: str,
        project_id: str,
        group_id: str,
        repository_id: str,
        *,
        user_id: str,
    ) -> str:
        return await self.gitlab_resources.ensure_repository_scope(
            connection_id, project_id, group_id, repository_id, user_id=user_id
        )

    async def get_gitlab_project(
        self,
        connection_id: str,
        project_id: str,
        repository_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        return await self.gitlab_resources.get_project(
            connection_id, project_id, repository_id, user_id=user_id
        )

    async def get_gitlab_branch(
        self,
        connection_id: str,
        project_id: str,
        repository_id: str,
        branch: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        return await self.gitlab_resources.get_branch(
            connection_id, project_id, repository_id, branch, user_id=user_id
        )

    async def resolve_gitlab_commit(
        self,
        connection_id: str,
        project_id: str,
        repository_id: str,
        ref: str,
        *,
        user_id: str,
    ) -> str:
        return await self.gitlab_resources.resolve_commit(
            connection_id, project_id, repository_id, ref, user_id=user_id
        )

    async def list_gitlab_groups(
        self,
        connection_id: str,
        *,
        user_id: str,
        project_id: str = "",
        search: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        return await self.gitlab_resources.list_groups(
            connection_id,
            user_id=user_id,
            project_id=project_id,
            search=search,
            page=page,
            page_size=page_size,
        )

    async def list_gitlab_group_repositories(
        self,
        connection_id: str,
        group_id: str,
        *,
        user_id: str,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        return await self.gitlab_resources.list_group_repositories(
            connection_id,
            group_id,
            user_id=user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )

    async def list_gitlab_repository_branches(
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
        return await self.gitlab_resources.list_repository_branches(
            connection_id,
            repository_id,
            user_id=user_id,
            project_id=project_id,
            search=search,
            page=page,
            page_size=page_size,
        )
