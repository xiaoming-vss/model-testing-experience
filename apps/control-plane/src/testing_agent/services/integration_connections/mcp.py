from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from testing_agent.core.enums import ConnectionStatus
from testing_agent.core.errors import ErrBadRequest
from testing_agent.services.integration_connections.common import ConnectionSupport


class McpConnectionCommands(ConnectionSupport):
    """MCP header-token connection commands."""

    async def _create_mcp(
        self,
        *,
        connection_id: str,
        body: dict[str, Any],
        user_id: str,
        project_id: str,
        commit: bool,
    ) -> dict:
        token = str(body.get("token") or "")
        if not token.strip():
            raise ErrBadRequest()
        return await self._store_new(
            connection_id=connection_id,
            project_id=project_id,
            user_id=user_id,
            provider="mcp",
            name=str(body["name"]),
            base_url=str(body["baseUrl"]),
            auth_type="mcp_header_token",
            account="",
            secret_json={"token": self._encrypt_secret(token)},
            access_token="",
            status=ConnectionStatus.ACTIVE.value,
            last_auth_at=datetime.now(UTC),
            last_auth_error="",
            extra_json={},
            commit=commit,
        )

    async def _update_mcp(
        self,
        connection,
        body: dict[str, Any],
        *,
        commit: bool,
    ) -> dict:
        if set(body) != {"token"} or not str(body["token"] or "").strip():
            raise ErrBadRequest()
        connection.secret_json = {"token": self._encrypt_secret(str(body["token"]))}
        connection.status = ConnectionStatus.ACTIVE.value
        connection.last_auth_at = datetime.now(UTC)
        return await self._finish_write(connection, commit=commit)
