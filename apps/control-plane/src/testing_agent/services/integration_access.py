"""Authorized connection lookup supplied to provider-specific resource queries."""

from typing import Protocol

from testing_agent.models.integration_connection import IntegrationConnection


class ActivePersonalConnection(Protocol):
    async def __call__(
        self, user_id: str, provider: str, connection_id: str, project_id: str = ""
    ) -> IntegrationConnection: ...
