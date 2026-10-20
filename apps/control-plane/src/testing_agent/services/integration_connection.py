from __future__ import annotations

from datetime import UTC, datetime
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
from testing_agent.services.gitlab_auth import GitLabAuthProvider, normalize_gitlab_base_url
from testing_agent.services.gitlab_queries import GitLabResources
from testing_agent.services.gitlab_resource import GitLabResourceClient
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.personal_credentials import PersonalCredentialAccess
from testing_agent.services.project_access import require_project_access
from testing_agent.services.service_instance import normalize_instance_url
from testing_agent.services.worker_authorization import revoke_executions
from testing_agent.services.zentao_auth import ZentaoAuthProvider
from testing_agent.services.zentao_queries import ZentaoResources
from testing_agent.services.zentao_queries import item_value as item_value
from testing_agent.services.zentao_queries import visible_zentao_items as visible_zentao_items
from testing_agent.services.zentao_queries import zentao_candidate_total as zentao_candidate_total
from testing_agent.services.zentao_queries import zentao_list_payload as zentao_list_payload
from testing_agent.services.zentao_resource import truncate_error


def dump_connection(connection: IntegrationConnection) -> dict[str, Any]:
    extra = connection.extra_json or {}
    secret = getattr(connection, "secret_json", None) or {}
    model_id = extra.get("modelId") or extra.get("model_id") or secret.get("modelId") or ""
    return {
        "connectionId": connection.connection_id,
        "projectId": getattr(connection, "project_id", ""),
        "provider": connection.provider,
        "name": extra.get("serviceName") or connection.name,
        "baseUrl": connection.base_url,
        "authType": connection.auth_type,
        "account": connection.account,
        "status": connection.status,
        "hasAccessToken": bool(connection.access_token or secret.get("apiKey")),
        "modelId": model_id,
        "lastAuthAt": connection.last_auth_at,
        "lastAuthError": connection.last_auth_error,
        "createdAt": connection.created_at,
        "updatedAt": connection.updated_at,
    }


class IntegrationConnectionService:
    def __init__(
        self,
        repository: IntegrationConnectionRepository,
        zentao_resource_client: Any | None = None,
        zentao_auth_provider: Any | None = None,
        gitlab_auth_provider: Any | None = None,
        gitlab_resource_client: Any | None = None,
        credential_cipher: IntegrationCredentialCipher | None = None,
    ):
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
        self, user_id: str, provider: str, connection_id: str, project_id: str = ""
    ) -> IntegrationConnection:
        connection = await self.repository.get(user_id, provider, connection_id, project_id)
        if connection is None:
            raise ErrNotFound()
        return connection

    async def resolve_zentao_access(
        self, user_id: str, connection_id: str, project_id: str = ""
    ) -> IntegrationConnection:
        connection = await self.get_active_personal(user_id, "zentao", connection_id, project_id)
        await self._ensure_zentao_token(connection)
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
        if provider == "zentao":
            name = str(body.get("name") or "").strip()
            base_url = str(body.get("baseUrl") or "").strip()
            account = str(body.get("account") or "").strip()
            password = str(body.get("password") or "")
            if not name or not base_url or not account or not password.strip():
                raise ErrBadRequest()
            auth_result = await self._authenticate_zentao(base_url, account, password)
            secret_json = {"password": self._encrypt_secret(body.get("password", ""))}
            extra_json: dict[str, Any] = {}
            auth_type = "account_password"
            access_token = auth_result.access_token
            status = ConnectionStatus.ACTIVE.value
            last_auth_at = datetime.now(UTC)
            last_auth_error = ""
            name_value = name
            base_url_value = base_url
            account_value = account
        elif provider == "mcp":
            token = str(body.get("token") or "")
            if not token.strip():
                raise ErrBadRequest()
            secret_json = {"token": self._encrypt_secret(token)}
            extra_json = {}
            auth_type = "mcp_header_token"
            access_token = ""
            status = ConnectionStatus.ACTIVE.value
            last_auth_at = datetime.now(UTC)
            last_auth_error = ""
            name_value = str(body["name"])
            base_url_value = str(body["baseUrl"])
            account_value = ""
        elif provider == "gitlab":
            name = str(body.get("name") or "").strip()
            base_url = self._normalize_gitlab_base_url(str(body.get("baseUrl") or ""))
            access_token_value = str(body.get("accessToken") or "").strip()
            if not name or not access_token_value:
                raise ErrBadRequest()
            await self._validate_gitlab(base_url, access_token_value)
            secret_json = {}
            extra_json = {}
            auth_type = "personal_access_token"
            access_token = self._encrypt_gitlab_token(access_token_value)
            status = ConnectionStatus.ACTIVE.value
            last_auth_at = datetime.now(UTC)
            last_auth_error = ""
            name_value = name
            base_url_value = base_url
            account_value = ""
        else:
            if not str(body.get("apiKey") or "").strip():
                raise ErrBadRequest()
            secret_json = {"apiKey": self._encrypt_secret(body.get("apiKey", ""))}
            extra_json = {"modelId": body.get("modelId", "")}
            auth_type = "api_key"
            access_token = ""
            status = str(body.get("status") or "active")
            last_auth_at = None
            last_auth_error = ""
            name_value = str(body.get("name") or f"{provider}-connection")
            base_url_value = str(body.get("baseUrl") or "")
            account_value = str(body.get("account") or "")
        connection = IntegrationConnection(
            connection_id=new_id(),
            project_id=project_id,
            user_id=user_id,
            provider=provider,
            name=name_value,
            base_url=base_url_value,
            auth_type=auth_type,
            account=account_value,
            secret_json=secret_json,
            access_token=access_token,
            status=status,
            last_auth_at=last_auth_at,
            last_auth_error=last_auth_error,
            extra_json=extra_json,
        )
        self.repository.add(connection)
        if commit:
            await self.repository.commit()
        else:
            await self.repository.session.flush()
        await self.repository.refresh(connection)
        return dump_connection(connection)

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
        from sqlalchemy import select

        from testing_agent.models.shared_service import ServiceAuthorization

        linked = await self.repository.session.scalar(
            select(ServiceAuthorization.id).where(
                ServiceAuthorization.connection_id == connection_id
            )
        )
        if linked and any(key in body for key in ("name", "baseUrl", "modelId")):
            raise ErrBadRequest()
        if provider == "gitlab":
            name = str(body.get("name", connection.name)).strip()
            if not name:
                raise ErrBadRequest()
            base_url = self._normalize_gitlab_base_url(
                str(body.get("baseUrl", connection.base_url))
            )
            credentials_changed = "baseUrl" in body or "accessToken" in body
            if "accessToken" in body:
                access_token = str(body["accessToken"] or "").strip()
                if not access_token:
                    raise ErrBadRequest()
            else:
                access_token = self._decrypt_gitlab_token(connection.access_token)
            if credentials_changed:
                await self._validate_gitlab(base_url, access_token)
            connection.name = name
            connection.base_url = base_url
            if "accessToken" in body:
                connection.access_token = self._encrypt_gitlab_token(access_token)
            if credentials_changed:
                connection.status = ConnectionStatus.ACTIVE.value
                connection.last_auth_at = datetime.now(UTC)
                connection.last_auth_error = ""
            if commit:
                await self.repository.commit()
            else:
                await self.repository.session.flush()
            await self.repository.refresh(connection)
            return dump_connection(connection)
        if provider == "mcp":
            if set(body) != {"token"} or not str(body["token"] or "").strip():
                raise ErrBadRequest()
            connection.secret_json = {"token": self._encrypt_secret(str(body["token"]))}
            connection.status = ConnectionStatus.ACTIVE.value
            connection.last_auth_at = datetime.now(UTC)
            if commit:
                await self.repository.commit()
            else:
                await self.repository.session.flush()
            await self.repository.refresh(connection)
            return dump_connection(connection)
        if "apiKey" in body and not str(body["apiKey"] or "").strip():
            raise ErrBadRequest()
        old_base_url = connection.base_url
        old_account = connection.account
        old_password = self._zentao_password(connection) if provider == "zentao" else ""
        for key, attr in {"name": "name", "baseUrl": "base_url", "account": "account"}.items():
            if key in body:
                setattr(connection, attr, body[key])
        if "password" in body:
            secret = dict(connection.secret_json or {})
            secret["password"] = self._encrypt_secret(str(body["password"]))
            connection.secret_json = secret
        if "apiKey" in body:
            secret = dict(connection.secret_json or {})
            secret["apiKey"] = self._encrypt_secret(str(body["apiKey"]))
            connection.secret_json = secret
        if "modelId" in body:
            extra = dict(connection.extra_json or {})
            extra["modelId"] = body["modelId"]
            connection.extra_json = extra
        if provider == "zentao" and (
            connection.base_url != old_base_url
            or connection.account != old_account
            or ("password" in body and body["password"] != old_password)
        ):
            password = self._zentao_password(connection)
            auth_result = await self._authenticate_zentao(
                connection.base_url,
                connection.account,
                password,
            )
            self._apply_zentao_auth_success(connection, auth_result)
        if commit:
            await self.repository.commit()
        else:
            await self.repository.session.flush()
        await self.repository.refresh(connection)
        return dump_connection(connection)

    async def reauth_zentao(
        self,
        connection_id: str,
        body: dict[str, Any] | None,
        user_id: str,
        project_id: str = "",
    ) -> dict:
        await self.ensure_project_access(user_id, project_id)
        connection = await self.get_owned(user_id, "zentao", connection_id, project_id)
        connection.status = ConnectionStatus.ACTIVE.value
        connection.last_auth_at = datetime.now(UTC)
        connection.last_auth_error = ""
        if body and body.get("password"):
            secret = connection.secret_json or {}
            secret["password"] = self._encrypt_secret(str(body["password"]))
            connection.secret_json = secret
        password = self._zentao_password(connection)
        try:
            auth_result = await self.zentao_auth_provider.authenticate(
                connection.base_url,
                connection.account,
                password,
            )
        except Exception as exc:
            self._apply_zentao_auth_failure(connection, str(exc))
            await self.repository.commit()
            await self.repository.refresh(connection)
            raise dynamic_error(
                ErrIntegrationConnectionAuthFailed,
                truncate_error(str(exc)),
            ) from exc
        self._apply_zentao_auth_success(connection, auth_result)
        await self.repository.commit()
        await self.repository.refresh(connection)
        return dump_connection(connection)

    async def reauth_gitlab(
        self,
        connection_id: str,
        body: dict[str, Any] | None,
        user_id: str,
        project_id: str = "",
    ) -> dict:
        await self.ensure_project_access(user_id, project_id)
        connection = await self.get_owned(user_id, "gitlab", connection_id, project_id)
        if body and "accessToken" in body:
            access_token = str(body["accessToken"] or "").strip()
            if not access_token:
                raise ErrBadRequest()
        else:
            access_token = self._decrypt_gitlab_token(connection.access_token)
        await self._validate_gitlab(connection.base_url, access_token)
        if body and "accessToken" in body:
            connection.access_token = self._encrypt_gitlab_token(access_token)
        connection.status = ConnectionStatus.ACTIVE.value
        connection.last_auth_at = datetime.now(UTC)
        connection.last_auth_error = ""
        await self.repository.commit()
        await self.repository.refresh(connection)
        return dump_connection(connection)

    async def delete(
        self, provider: str, connection_id: str, user_id: str, project_id: str = ""
    ) -> dict:
        await self.ensure_project_access(user_id, project_id)
        connection = await self.get_owned(user_id, provider, connection_id, project_id)
        await revoke_executions(self.repository.session, actor=user_id, connection_id=connection_id)
        await self.repository.hard_delete(connection)
        await self.repository.commit()
        return {}

    async def list_zentao_projects(
        self,
        connection_id: str,
        user_id: str,
        *,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        return await self.zentao_resources.list_projects(
            connection_id, user_id, project_id=project_id, page=page, page_size=page_size
        )

    async def resolve_gitlab_group_id(
        self, connection_id: str, project_id: str, group_id: str, *, user_id: str
    ) -> str:
        return await self.gitlab_resources.resolve_group_id(
            connection_id, project_id, group_id, user_id=user_id
        )

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

    async def list_zentao_project_executions(
        self,
        connection_id: str,
        remote_project_id: str,
        user_id: str,
        *,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        return await self.zentao_resources.list_project_executions(
            connection_id,
            remote_project_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )

    async def list_zentao_execution_testtasks(
        self,
        connection_id: str,
        remote_execution_id: str,
        user_id: str,
        *,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        return await self.zentao_resources.list_execution_testtasks(
            connection_id,
            remote_execution_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )

    async def list_zentao_execution_stories(
        self,
        connection_id: str,
        remote_execution_id: str,
        user_id: str,
        project_id: str = "",
    ) -> dict:
        return await self.zentao_resources.list_execution_stories(
            connection_id, remote_execution_id, user_id, project_id
        )

    async def list_zentao_execution_cases(
        self,
        connection_id: str,
        remote_execution_id: str,
        user_id: str,
        *,
        project_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        return await self.zentao_resources.list_execution_cases(
            connection_id,
            remote_execution_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )

    async def _ensure_zentao_token(self, connection: IntegrationConnection) -> None:
        if connection.access_token and connection.status == ConnectionStatus.ACTIVE.value:
            return
        password = self._zentao_password(connection)
        try:
            auth_result = await self.zentao_auth_provider.authenticate(
                connection.base_url,
                connection.account,
                password,
            )
        except Exception as exc:
            self._apply_zentao_auth_failure(connection, str(exc))
            await self.repository.commit()
            raise dynamic_error(
                ErrIntegrationConnectionAuthFailed,
                truncate_error(str(exc)),
            ) from exc
        self._apply_zentao_auth_success(connection, auth_result)
        await self.repository.commit()

    async def _authenticate_zentao(self, base_url: str, account: str, password: str) -> Any:
        try:
            return await self.zentao_auth_provider.authenticate(base_url, account, password)
        except Exception as exc:
            raise dynamic_error(
                ErrIntegrationConnectionAuthFailed,
                truncate_error(str(exc)),
            ) from exc

    async def _validate_gitlab(self, base_url: str, access_token: str) -> None:
        try:
            await self.gitlab_auth_provider.validate(base_url, access_token)
        except Exception as exc:
            raise dynamic_error(
                ErrIntegrationConnectionAuthFailed,
                truncate_error(str(exc)),
            ) from exc

    def _encrypt_gitlab_token(self, access_token: str) -> str:
        return self._encrypt_secret(access_token)

    def _decrypt_gitlab_token(self, access_token: str) -> str:
        return self._decrypt_secret(access_token)

    def _encrypt_secret(self, plaintext: str) -> str:
        if self.credential_cipher is None:
            raise RuntimeError("未配置集成凭据加密器")
        return self.credential_cipher.encrypt(plaintext)

    def _decrypt_secret(self, ciphertext: str) -> str:
        if self.credential_cipher is None:
            raise RuntimeError("未配置集成凭据加密器")
        return self.credential_cipher.decrypt(ciphertext)

    def _normalize_gitlab_base_url(self, base_url: str) -> str:
        try:
            return normalize_gitlab_base_url(base_url)
        except ValueError as exc:
            raise ErrBadRequest() from exc

    def _zentao_password(self, connection: IntegrationConnection) -> str:
        secret = connection.secret_json or {}
        password = str(secret.get("password") or "")
        if password.strip():
            password = self._decrypt_secret(password)
        if not password.strip():
            raise ErrBadRequest()
        return password

    def _apply_zentao_auth_success(
        self,
        connection: IntegrationConnection,
        auth_result: Any,
    ) -> None:
        connection.access_token = str(getattr(auth_result, "access_token", "") or "")
        connection.status = ConnectionStatus.ACTIVE.value
        connection.last_auth_at = datetime.now(UTC)
        connection.last_auth_error = ""

    def _apply_zentao_auth_failure(self, connection: IntegrationConnection, message: str) -> None:
        connection.access_token = ""
        connection.status = ConnectionStatus.AUTH_FAILED.value
        connection.last_auth_error = truncate_error(message)

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
