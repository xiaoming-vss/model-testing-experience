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
from testing_agent.services.integration_connections.common import ConnectionSupport, dump_connection
from testing_agent.services.zentao_resource import truncate_error


class ZentaoConnectionCommands(ConnectionSupport):
    """Zentao credential, authentication and resource-query commands."""

    async def _create_zentao(
        self,
        *,
        connection_id: str,
        body: dict[str, Any],
        user_id: str,
        project_id: str,
        commit: bool,
    ) -> dict:
        name = str(body.get("name") or "").strip()
        base_url = str(body.get("baseUrl") or "").strip()
        account = str(body.get("account") or "").strip()
        password = str(body.get("password") or "")
        allow_http, insecure_skip_verify = self._security_flags(body)
        if not name or not base_url or not account or not password.strip():
            raise ErrBadRequest()
        self._require_secure_scheme(base_url, allow_http)
        if commit:
            # Do not hold the read transaction opened by the access check
            # while waiting for the external authentication service.
            await self.repository.session.commit()
        auth_result = await self._authenticate_zentao(
            base_url,
            account,
            password,
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        await self.ensure_project_access(user_id, project_id)
        return await self._store_new(
            connection_id=connection_id,
            project_id=project_id,
            user_id=user_id,
            provider="zentao",
            name=name,
            base_url=base_url,
            auth_type="account_password",
            account=account,
            secret_json={"password": self._encrypt_secret(body.get("password", ""))},
            access_token=auth_result.access_token,
            status=ConnectionStatus.ACTIVE.value,
            last_auth_at=datetime.now(UTC),
            last_auth_error="",
            extra_json={
                "allowHttp": allow_http,
                "insecureSkipVerify": insecure_skip_verify,
            },
            commit=commit,
        )

    async def _update_zentao(
        self,
        connection: IntegrationConnection,
        connection_id: str,
        body: dict[str, Any],
        user_id: str,
        project_id: str,
        *,
        commit: bool,
    ) -> dict:
        fields = self._candidate_update(connection, body, "zentao")
        old_password = self._zentao_password(connection)
        credentials_changed = (
            fields.base_url != connection.base_url
            or fields.account != connection.account
            or ("password" in body and body["password"] != old_password)
            or fields.flags_changed
        )
        auth_result = None
        if credentials_changed:
            self._require_secure_scheme(fields.base_url, fields.allow_http)
            password = (
                str(body["password"]) if "password" in body else self._zentao_password(connection)
            )
            expected_updated_at = connection.updated_at
            # End the read transaction before waiting on the external service.
            if commit:
                await self.repository.commit()
            auth_result = await self._authenticate_zentao(
                fields.base_url,
                fields.account,
                password,
                allow_http=fields.allow_http,
                insecure_skip_verify=fields.insecure_skip_verify,
            )
            connection = await self._reload_locked(
                user_id,
                "zentao",
                connection_id,
                project_id,
                expected_updated_at=expected_updated_at,
            )
        self._apply_update_fields(connection, fields)
        if auth_result is not None:
            self._apply_zentao_auth_success(connection, auth_result)
        return await self._finish_write(connection, commit=commit)

    async def reauth_zentao(
        self,
        connection_id: str,
        body: dict[str, Any] | None,
        user_id: str,
        project_id: str = "",
    ) -> dict:
        await self.ensure_project_access(user_id, project_id)
        connection = await self.get_owned(user_id, "zentao", connection_id, project_id)
        if body and body.get("password"):
            password = str(body["password"])
        else:
            password = self._zentao_password(connection)
        allow_http, insecure_skip_verify = connection_security_flags(connection.extra_json)
        self._require_secure_scheme(connection.base_url, allow_http)
        base_url = connection.base_url
        account = connection.account
        expected_updated_at = connection.updated_at
        # End the read transaction before waiting on the external service.
        await self.repository.commit()
        try:
            auth_result = await self.zentao_auth_provider.authenticate(
                base_url,
                account,
                password,
                allow_http=allow_http,
                insecure_skip_verify=insecure_skip_verify,
            )
        except Exception as exc:
            connection = await self._reload_locked(
                user_id,
                "zentao",
                connection_id,
                project_id,
                expected_updated_at=expected_updated_at,
            )
            if body and body.get("password"):
                secret = dict(connection.secret_json or {})
                secret["password"] = self._encrypt_secret(str(body["password"]))
                connection.secret_json = secret
            self._apply_zentao_auth_failure(connection, str(exc))
            await self.repository.commit()
            await self.repository.refresh(connection)
            raise dynamic_error(
                ErrIntegrationConnectionAuthFailed,
                truncate_error(str(exc)),
            ) from exc
        connection = await self._reload_locked(
            user_id,
            "zentao",
            connection_id,
            project_id,
            expected_updated_at=expected_updated_at,
        )
        if body and body.get("password"):
            secret = dict(connection.secret_json or {})
            secret["password"] = self._encrypt_secret(str(body["password"]))
            connection.secret_json = secret
        self._apply_zentao_auth_success(connection, auth_result)
        await self.repository.commit()
        await self.repository.refresh(connection)
        return dump_connection(connection)

    async def resolve_zentao_access(
        self, user_id: str, connection_id: str, project_id: str = ""
    ) -> IntegrationConnection:
        connection = await self.get_active_personal(user_id, "zentao", connection_id, project_id)
        await self._ensure_zentao_token(connection)
        return connection

    async def _ensure_zentao_token(self, connection: IntegrationConnection) -> None:
        if connection.access_token and connection.status == ConnectionStatus.ACTIVE.value:
            return
        password = self._zentao_password(connection)
        allow_http, insecure_skip_verify = connection_security_flags(
            getattr(connection, "extra_json", None)
        )
        self._require_secure_scheme(connection.base_url, allow_http)
        try:
            auth_result = await self.zentao_auth_provider.authenticate(
                connection.base_url,
                connection.account,
                password,
                allow_http=allow_http,
                insecure_skip_verify=insecure_skip_verify,
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

    async def _authenticate_zentao(
        self,
        base_url: str,
        account: str,
        password: str,
        *,
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
    ) -> Any:
        try:
            return await self.zentao_auth_provider.authenticate(
                base_url,
                account,
                password,
                allow_http=allow_http,
                insecure_skip_verify=insecure_skip_verify,
            )
        except Exception as exc:
            raise dynamic_error(
                ErrIntegrationConnectionAuthFailed,
                truncate_error(str(exc)),
            ) from exc

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
