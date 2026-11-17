from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrMonitoringConnectionDisabled,
    ErrMonitoringConnectionNameAlreadyUse,
    ErrMonitoringConnectionNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.models.monitoring_connection import MonitoringConnection
from testing_agent.repositories.monitoring_connection import MonitoringConnectionRepository
from testing_agent.schemas.monitoring_connection import (
    MonitoringAuthRequest,
    MonitoringAuthType,
    MonitoringConnectionCreate,
    MonitoringConnectionResponse,
    MonitoringConnectionUpdate,
)
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.project_access import ProjectAction, require_project_id


class MonitoringConnectionService:
    def __init__(
        self,
        repository: MonitoringConnectionRepository,
        *,
        credential_cipher: IntegrationCredentialCipher,
    ) -> None:
        self.repository = repository
        self.credential_cipher = credential_cipher

    async def _require_project(self, user_id: str, project_id: str, action: ProjectAction) -> None:
        await require_project_id(self.repository.session, user_id, project_id, action=action)

    async def _accessible(
        self, user_id: str, connection_id: str, *, action: ProjectAction
    ) -> MonitoringConnection:
        connection = await self.repository.get_connection(connection_id)
        if connection is None:
            raise ErrMonitoringConnectionNotFound()
        await self._require_project(user_id, connection.project_id, action)
        return connection

    def _encode_auth(self, auth: MonitoringAuthRequest) -> dict[str, Any] | None:
        if auth.type == "none":
            return None
        if auth.type == "basic":
            return {
                "username": auth.username,
                "password": self.credential_cipher.encrypt(auth.password.get_secret_value()),
            }
        if auth.type == "bearer":
            return {"token": self.credential_cipher.encrypt(auth.token.get_secret_value())}
        return {
            "headers": {
                name: self.credential_cipher.encrypt(value) for name, value in auth.headers.items()
            }
        }

    def _decrypt_auth(self, auth_type: str, secret: dict[str, Any] | None) -> dict[str, Any]:
        if auth_type == "none":
            return {"type": "none"}
        if not secret:
            raise AppError(409, "监控接入凭据缺失，请重新配置", 409)
        try:
            if auth_type == "basic":
                return {
                    "type": "basic",
                    "username": str(secret.get("username", "")),
                    "password": self.credential_cipher.decrypt(str(secret["password"])),
                }
            if auth_type == "bearer":
                return {
                    "type": "bearer",
                    "token": self.credential_cipher.decrypt(str(secret["token"])),
                }
            if auth_type == "headers":
                headers = secret.get("headers") or {}
                return {
                    "type": "headers",
                    "headers": {
                        name: self.credential_cipher.decrypt(str(value))
                        for name, value in headers.items()
                    },
                }
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(409, "监控接入凭据无法解密，请重新配置", 409) from exc
        raise AppError(409, "监控接入认证方式不合法，请重新配置", 409)

    def remote_write_auth(self, connection: MonitoringConnection) -> dict[str, Any]:
        return self._decrypt_auth(
            connection.remote_write_auth_type, connection.remote_write_secret_json
        )

    def secret_values(self, connection: MonitoringConnection) -> list[str]:
        values: list[str] = []
        for auth_type, secret in (
            (connection.query_auth_type, connection.query_secret_json),
            (connection.remote_write_auth_type, connection.remote_write_secret_json),
        ):
            if not secret:
                continue
            if auth_type == "basic":
                value = secret.get("password")
                if value:
                    values.append(self.credential_cipher.decrypt(str(value)))
            elif auth_type == "bearer":
                value = secret.get("token")
                if value:
                    values.append(self.credential_cipher.decrypt(str(value)))
            elif auth_type == "headers":
                for value in (secret.get("headers") or {}).values():
                    values.append(self.credential_cipher.decrypt(str(value)))
        return values

    def _response(self, connection: MonitoringConnection) -> dict[str, Any]:
        response = MonitoringConnectionResponse(
            connection_id=connection.connection_id,
            project_id=connection.project_id,
            name=connection.name,
            query_url=connection.query_url,
            remote_write_url=connection.remote_write_url,
            query_auth_type=cast(MonitoringAuthType, connection.query_auth_type),
            remote_write_auth_type=cast(MonitoringAuthType, connection.remote_write_auth_type),
            has_query_credentials=bool(connection.query_secret_json),
            has_remote_write_credentials=bool(connection.remote_write_secret_json),
            grafana_url=connection.grafana_url,
            grafana_dashboard_uid=connection.grafana_dashboard_uid,
            default_filters=connection.default_filters_json or {},
            enabled=connection.enabled,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
        )
        return response.model_dump(by_alias=True, mode="json")

    async def create(
        self, user_id: str, project_id: str, body: MonitoringConnectionCreate
    ) -> dict[str, Any]:
        await self._require_project(user_id, project_id, "manage")
        if await self.repository.get_by_project_and_name(project_id, body.name) is not None:
            raise ErrMonitoringConnectionNameAlreadyUse()
        connection = MonitoringConnection(
            connection_id=new_id(),
            project_id=project_id,
            name=body.name,
            query_url=body.query_url,
            remote_write_url=body.remote_write_url,
            query_auth_type=body.query_auth.type,
            query_secret_json=self._encode_auth(body.query_auth),
            remote_write_auth_type=body.remote_write_auth.type,
            remote_write_secret_json=self._encode_auth(body.remote_write_auth),
            grafana_url=body.grafana_url,
            grafana_dashboard_uid=body.grafana_dashboard_uid,
            default_filters_json=body.default_filters,
            enabled=body.enabled,
            created_by=user_id,
        )
        self.repository.add(connection)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ErrMonitoringConnectionNameAlreadyUse() from exc
        await self.repository.refresh(connection)
        return self._response(connection)

    async def list(self, user_id: str, project_id: str) -> dict[str, Any]:
        await self._require_project(user_id, project_id, "read")
        rows = await self.repository.list_by_project(project_id)
        return {"total": len(rows), "items": [self._response(row) for row in rows]}

    async def get(self, user_id: str, connection_id: str) -> dict[str, Any]:
        return self._response(await self._accessible(user_id, connection_id, action="read"))

    async def update(
        self, user_id: str, connection_id: str, body: MonitoringConnectionUpdate
    ) -> dict[str, Any]:
        connection = await self._accessible(user_id, connection_id, action="manage")
        fields = body.model_fields_set
        if "name" in fields:
            name = body.name
            if name is None:
                raise ErrBadRequest()
            if name != connection.name and (
                await self.repository.get_by_project_and_name(connection.project_id, name)
                is not None
            ):
                raise ErrMonitoringConnectionNameAlreadyUse()
            connection.name = name
        if "query_url" in fields and body.query_url is not None:
            connection.query_url = body.query_url
        if "remote_write_url" in fields and body.remote_write_url is not None:
            connection.remote_write_url = body.remote_write_url
        if "query_auth" in fields:
            auth = body.query_auth or MonitoringAuthRequest()
            connection.query_auth_type = auth.type
            connection.query_secret_json = self._encode_auth(auth)
        if "remote_write_auth" in fields:
            auth = body.remote_write_auth or MonitoringAuthRequest()
            connection.remote_write_auth_type = auth.type
            connection.remote_write_secret_json = self._encode_auth(auth)
        if "grafana_url" in fields and body.grafana_url is not None:
            connection.grafana_url = body.grafana_url
        if "grafana_dashboard_uid" in fields and body.grafana_dashboard_uid is not None:
            connection.grafana_dashboard_uid = body.grafana_dashboard_uid
        if "default_filters" in fields and body.default_filters is not None:
            connection.default_filters_json = body.default_filters
        if "enabled" in fields and body.enabled is not None:
            connection.enabled = body.enabled
        connection.updated_at = datetime.now(UTC)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ErrMonitoringConnectionNameAlreadyUse() from exc
        await self.repository.refresh(connection)
        return self._response(connection)

    async def delete(self, user_id: str, connection_id: str) -> dict[str, Any]:
        connection = await self._accessible(user_id, connection_id, action="manage")
        await self.repository.session.delete(connection)
        await self.repository.commit()
        return {}

    def require_enabled(self, connection: MonitoringConnection | None) -> MonitoringConnection:
        if connection is None:
            raise ErrMonitoringConnectionNotFound()
        if not connection.enabled:
            raise ErrMonitoringConnectionDisabled()
        return connection
