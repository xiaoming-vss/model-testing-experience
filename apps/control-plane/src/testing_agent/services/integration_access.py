"""Authorized connection lookup supplied to provider-specific resource queries."""

from typing import Protocol

from testing_agent.models.integration_connection import IntegrationConnection


class ActivePersonalConnection(Protocol):
    async def __call__(
        self, user_id: str, provider: str, connection_id: str, project_id: str = ""
    ) -> IntegrationConnection: ...


class EnsureZentaoToken(Protocol):
    """Refresh an authorized connection before reading remote candidates.

    An expired/missing token may commit its authentication result through the
    connection manager, preserving the existing refresh transaction. Resource
    reads must call this before any later business write transaction begins.
    """

    async def __call__(self, connection: IntegrationConnection) -> None: ...
