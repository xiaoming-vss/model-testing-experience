from __future__ import annotations

from typing import Any

from testing_agent.core.enums import ConnectionStatus
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrIntegrationConnectionAuthFailed,
    ErrNotFound,
    ErrResourceBindingInvalid,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.repositories.integration_connection import IntegrationConnectionRepository
from testing_agent.services.common import list_payload
from testing_agent.services.gitlab_auth import GitLabAuthProvider
from testing_agent.services.gitlab_queries import GitLabResources
from testing_agent.services.gitlab_resource import GitLabResourceClient
from testing_agent.services.integration_connections.common import dump_connection
from testing_agent.services.integration_connections.gitlab import GitLabConnectionCommands
from testing_agent.services.integration_connections.llm import ApiKeyConnectionCommands
from testing_agent.services.integration_connections.mcp import McpConnectionCommands
from testing_agent.services.integration_connections.zentao import ZentaoConnectionCommands
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.personal_credentials import PersonalCredentialAccess
from testing_agent.services.project_access import require_project_access
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion
from testing_agent.services.service_instance import normalize_instance_url
from testing_agent.services.worker_authorization import (
    notify_revoked_executions,
    revoke_executions,
)
from testing_agent.services.zentao_auth import ZentaoAuthProvider
from testing_agent.services.zentao_queries import ZentaoResources
from testing_agent.services.zentao_queries import item_value as item_value
from testing_agent.services.zentao_queries import visible_zentao_items as visible_zentao_items
from testing_agent.services.zentao_queries import zentao_candidate_total as zentao_candidate_total
from testing_agent.services.zentao_queries import zentao_list_payload as zentao_list_payload


class IntegrationConnectionService(
    ZentaoConnectionCommands,
    GitLabConnectionCommands,
    McpConnectionCommands,
    ApiKeyConnectionCommands,
):
    def __init__(
        self,
        repository: IntegrationConnectionRepository,
        zentao_resource_client: Any | None = None,
        zentao_auth_provider: Any | None = None,
        gitlab_auth_provider: Any | None = None,
        gitlab_resource_client: Any | None = None,
        credential_cipher: IntegrationCredentialCipher | None = None,
        *,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.deletion = deletion or SqlResourceDeletion()
        self.repository = repository
        self.zentao_resource_client = zentao_resource_client
        self.zentao_auth_provider = zentao_auth_provider or ZentaoAuthProvider()
        self.gitlab_auth_provider = gitlab_auth_provider or GitLabAuthProvider()
        self.gitlab_resource_client = gitlab_resource_client or GitLabResourceClient()
        self.credential_cipher = credential_cipher
        self.credentials = PersonalCredentialAccess(credential_cipher)
        self.zentao_resources = ZentaoResources(
            authorize=self.get_active_personal,
            ensure_token=self._ensure_zentao_token,
            client=self.zentao_resource_client,
        )
        self.gitlab_resources = GitLabResources(
            authorize=self.get_active_personal,
            credentials=self.credentials,
            client=self.gitlab_resource_client,
        )

    async def get_owned(
        self,
        user_id: str,
        provider: str,
        connection_id: str,
        project_id: str = "",
        *,
        lock: bool = False,
    ) -> IntegrationConnection:
        connection = await self.repository.get(
            user_id, provider, connection_id, project_id, lock=lock
        )
        if connection is None:
            raise ErrNotFound()
        return connection

    async def ensure_project_access(self, user_id: str, project_id: str) -> None:
        if not project_id:
            return
        project = await self.repository.get_project(project_id)
        if project is None:
            raise ErrNotFound()
        await require_project_access(self.repository.session, user_id, project)

    async def create(
        self,
        provider: str,
        body: dict[str, Any],
        user_id: str,
        project_id: str = "",
        *,
        commit: bool = True,
    ) -> dict:
        project_id = str(project_id or body.get("projectId") or body.get("project_id") or "")
        await self.ensure_project_access(user_id, project_id)
        connection_id = new_id()
        if provider == "zentao":
            return await self._create_zentao(
                connection_id=connection_id,
                body=body,
                user_id=user_id,
                project_id=project_id,
                commit=commit,
            )
        if provider == "mcp":
            return await self._create_mcp(
                connection_id=connection_id,
                body=body,
                user_id=user_id,
                project_id=project_id,
                commit=commit,
            )
        if provider == "gitlab":
            return await self._create_gitlab(
                connection_id=connection_id,
                body=body,
                user_id=user_id,
                project_id=project_id,
                commit=commit,
            )
        return await self._create_api_key(
            connection_id=connection_id,
            provider=provider,
            body=body,
            user_id=user_id,
            project_id=project_id,
            commit=commit,
        )

    async def list(self, provider: str, user_id: str, project_id: str = "") -> dict[str, Any]:
        await self.ensure_project_access(user_id, project_id)
        rows = await self.repository.list(user_id, provider, project_id)
        return list_payload([dump_connection(row) for row in rows])

    async def get(
        self, provider: str, connection_id: str, user_id: str, project_id: str = ""
    ) -> dict:
        await self.ensure_project_access(user_id, project_id)
        return dump_connection(await self.get_owned(user_id, provider, connection_id, project_id))

    async def update(
        self,
        provider: str,
        connection_id: str,
        body: dict[str, Any],
        user_id: str,
        project_id: str = "",
        *,
        commit: bool = True,
    ) -> dict:
        await self.ensure_project_access(user_id, project_id)
        connection = await self.get_owned(user_id, provider, connection_id, project_id)
        if any(value is None for value in body.values()):
            # Explicit null is not a supported clear signal for connections;
            # callers must omit a field to keep it unchanged.
            raise ErrBadRequest()
        from sqlalchemy import select

        from testing_agent.models.shared_service import ServiceAuthorization

        # transaction-bound: the linked-authorization check must see the same
        # transaction as the update; moving it to a repository would not change
        # that boundary, so it stays next to the update command.
        linked = await self.repository.session.scalar(
            select(ServiceAuthorization.id).where(
                ServiceAuthorization.connection_id == connection_id
            )
        )
        if linked and any(key in body for key in ("name", "baseUrl", "modelId")):
            raise ErrBadRequest()
        if provider == "gitlab":
            return await self._update_gitlab(
                connection, connection_id, body, user_id, project_id, commit=commit
            )
        if provider == "mcp":
            return await self._update_mcp(connection, body, commit=commit)
        if provider == "zentao":
            return await self._update_zentao(
                connection, connection_id, body, user_id, project_id, commit=commit
            )
        return await self._update_api_key(connection, body, provider, commit=commit)

    async def delete(
        self, provider: str, connection_id: str, user_id: str, project_id: str = ""
    ) -> dict:
        await self.ensure_project_access(user_id, project_id)
        connection = await self.get_owned(user_id, provider, connection_id, project_id)
        revoked = await revoke_executions(
            self.repository.session, actor=user_id, connection_id=connection_id
        )
        await self.deletion.delete(self.repository.session, connection)
        await self.repository.commit()
        await notify_revoked_executions(revoked)
        return {}

    async def get_active_personal(
        self, user_id: str, provider: str, connection_id: str, project_id: str = ""
    ) -> IntegrationConnection:
        await self.ensure_project_access(user_id, project_id)
        connection = await self.get_owned(user_id, provider, connection_id, project_id)
        if connection.status != ConnectionStatus.ACTIVE.value:
            raise ErrIntegrationConnectionAuthFailed()
        return connection

    async def resolve_personal_connection(
        self,
        user_id: str,
        provider: str,
        project_id: str,
        instance_url: str,
        connection_id: str = "",
    ) -> IntegrationConnection:
        await self.ensure_project_access(user_id, project_id)
        instance = normalize_instance_url(instance_url)
        if connection_id:
            connection = await self.get_active_personal(
                user_id, provider, connection_id, project_id
            )
            if normalize_instance_url(connection.base_url) != instance:
                raise ErrResourceBindingInvalid()
            return connection
        candidates = await self.repository.list(user_id, provider)
        matching = [
            c
            for c in candidates
            if c.project_id in ("", project_id)
            and normalize_instance_url(c.base_url) == instance
            and c.status == ConnectionStatus.ACTIVE.value
        ]
        if len(matching) != 1:
            raise dynamic_error(
                ErrIntegrationConnectionAuthFailed, "请配置并明确选择本人在该服务实例的有效连接"
            )
        return matching[0]
