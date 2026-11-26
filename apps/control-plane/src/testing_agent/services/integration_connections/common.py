from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrIntegrationConnectionAuthFailed,
    dynamic_error,
)
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.services.connection_security import (
    connection_security_flags,
    require_secure_scheme,
)
from testing_agent.services.gitlab_auth import normalize_gitlab_base_url


def dump_connection(connection: IntegrationConnection) -> dict[str, Any]:
    extra = connection.extra_json or {}
    secret = getattr(connection, "secret_json", None) or {}
    model_id = extra.get("modelId") or extra.get("model_id") or secret.get("modelId") or ""
    allow_http, insecure_skip_verify = connection_security_flags(extra)
    return {
        "connectionId": connection.connection_id,
        "projectId": getattr(connection, "project_id", ""),
        "provider": connection.provider,
        "name": extra.get("serviceName") or connection.name,
        "baseUrl": connection.base_url,
        "allowHttp": allow_http,
        "insecureSkipVerify": insecure_skip_verify,
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


@dataclass(slots=True)
class UpdateFields:
    name: Any
    base_url: Any
    account: Any
    secret: dict[str, Any]
    secret_changed: bool
    extra: dict[str, Any]
    extra_changed: bool


class ConnectionSupport:
    """Shared persistence, credential and transaction helpers for connection commands."""

    repository: Any
    credential_cipher: Any
    gitlab_auth_provider: Any
    gitlab_resources: Any

    async def get_owned(
        self,
        user_id: str,
        provider: str,
        connection_id: str,
        project_id: str = "",
        *,
        lock: bool = False,
    ) -> IntegrationConnection:
        raise NotImplementedError

    async def ensure_project_access(self, user_id: str, project_id: str) -> None:
        raise NotImplementedError

    async def get_active_personal(
        self, user_id: str, provider: str, connection_id: str, project_id: str = ""
    ) -> IntegrationConnection:
        raise NotImplementedError

    async def _store_new(
        self,
        *,
        connection_id: str,
        project_id: str,
        user_id: str,
        provider: str,
        name: Any,
        base_url: Any,
        auth_type: str,
        account: Any,
        secret_json: dict[str, Any],
        access_token: str,
        status: str,
        last_auth_at: datetime | None,
        last_auth_error: str,
        extra_json: dict[str, Any],
        commit: bool,
    ) -> dict:
        connection = IntegrationConnection(
            connection_id=connection_id,
            project_id=project_id,
            user_id=user_id,
            provider=provider,
            name=name,
            base_url=base_url,
            auth_type=auth_type,
            account=account,
            secret_json=secret_json,
            access_token=access_token,
            status=status,
            last_auth_at=last_auth_at,
            last_auth_error=last_auth_error,
            extra_json=extra_json,
        )
        self.repository.add(connection)
        return await self._finish_write(connection, commit=commit)

    async def _finish_write(self, connection: IntegrationConnection, *, commit: bool) -> dict:
        if commit:
            await self.repository.commit()
        else:
            await self.repository.session.flush()
        await self.repository.refresh(connection)
        return dump_connection(connection)

    async def _reload_locked(
        self,
        user_id: str,
        provider: str,
        connection_id: str,
        project_id: str,
        *,
        expected_updated_at: datetime | None,
    ) -> IntegrationConnection:
        connection = await self.get_owned(user_id, provider, connection_id, project_id, lock=True)
        if connection.updated_at != expected_updated_at:
            raise AppError(409, "集成连接在外部认证期间已被修改，请重试", 409)
        return connection

    def _candidate_update(
        self, connection: IntegrationConnection, body: dict[str, Any]
    ) -> UpdateFields:
        if "apiKey" in body and not str(body["apiKey"] or "").strip():
            raise ErrBadRequest()
        secret = dict(connection.secret_json or {})
        secret_changed = "apiKey" in body
        if secret_changed:
            secret["apiKey"] = self._encrypt_secret(str(body["apiKey"]))
        extra = dict(connection.extra_json or {})
        extra_changed = "modelId" in body
        if extra_changed:
            extra["modelId"] = body["modelId"]
        return UpdateFields(
            name=body.get("name", connection.name),
            base_url=body.get("baseUrl", connection.base_url),
            account=body.get("account", connection.account),
            secret=secret,
            secret_changed=secret_changed,
            extra=extra,
            extra_changed=extra_changed,
        )

    @staticmethod
    def _apply_update_fields(connection: IntegrationConnection, fields: UpdateFields) -> None:
        connection.name = fields.name
        connection.base_url = fields.base_url
        connection.account = fields.account
        if fields.extra_changed:
            connection.extra_json = fields.extra
        if fields.secret_changed:
            connection.secret_json = fields.secret

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
        try:
            return self.credential_cipher.decrypt(ciphertext)
        except ValueError as exc:
            raise dynamic_error(
                ErrIntegrationConnectionAuthFailed, "集成凭据解密失败,请重新授权该连接"
            ) from exc

    @staticmethod
    def _security_flags(body: dict[str, Any]) -> tuple[bool, bool]:
        return (
            bool(body.get("allowHttp", body.get("allow_http", False))),
            bool(body.get("insecureSkipVerify", body.get("insecure_skip_verify", False))),
        )

    @staticmethod
    def _updated_security_flags(
        connection: IntegrationConnection, body: dict[str, Any]
    ) -> tuple[bool, bool]:
        allow_http, insecure_skip_verify = connection_security_flags(
            getattr(connection, "extra_json", None)
        )
        if "allowHttp" in body or "allow_http" in body:
            allow_http = bool(body.get("allowHttp", body.get("allow_http")))
        if "insecureSkipVerify" in body or "insecure_skip_verify" in body:
            insecure_skip_verify = bool(
                body.get("insecureSkipVerify", body.get("insecure_skip_verify"))
            )
        return allow_http, insecure_skip_verify

    @staticmethod
    def _require_secure_scheme(base_url: str, allow_http: bool) -> None:
        try:
            require_secure_scheme(base_url, allow_http=allow_http)
        except ValueError as exc:
            raise ErrBadRequest() from exc

    def _normalize_gitlab_base_url(self, base_url: str) -> str:
        try:
            return normalize_gitlab_base_url(base_url)
        except ValueError as exc:
            raise ErrBadRequest() from exc
