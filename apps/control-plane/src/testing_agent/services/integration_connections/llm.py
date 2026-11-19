from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrBadRequest
from testing_agent.services.integration_connections.common import ConnectionSupport


class ApiKeyConnectionCommands(ConnectionSupport):
    """LLM and other API-key connection commands."""

    async def _create_api_key(
        self,
        *,
        connection_id: str,
        provider: str,
        body: dict[str, Any],
        user_id: str,
        project_id: str,
        commit: bool,
    ) -> dict:
        if not str(body.get("apiKey") or "").strip():
            raise ErrBadRequest()
        return await self._store_new(
            connection_id=connection_id,
            project_id=project_id,
            user_id=user_id,
            provider=provider,
            name=str(body.get("name") or f"{provider}-connection"),
            base_url=str(body.get("baseUrl") or ""),
            auth_type="api_key",
            account=str(body.get("account") or ""),
            secret_json={"apiKey": self._encrypt_secret(body.get("apiKey", ""))},
            access_token="",
            status=str(body.get("status") or "active"),
            last_auth_at=None,
            last_auth_error="",
            extra_json={"modelId": body.get("modelId", "")},
            commit=commit,
        )

    async def _update_api_key(
        self,
        connection,
        body: dict[str, Any],
        provider: str,
        *,
        commit: bool,
    ) -> dict:
        fields = self._candidate_update(connection, body, provider)
        self._apply_update_fields(connection, fields)
        return await self._finish_write(connection, commit=commit)
