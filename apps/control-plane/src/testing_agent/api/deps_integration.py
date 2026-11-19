from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.config import Settings, get_settings
from testing_agent.db.session import get_session
from testing_agent.repositories.bug import BugRepository
from testing_agent.repositories.integration_connection import IntegrationConnectionRepository
from testing_agent.services.bug import BugService
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher


def get_integration_connection_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> IntegrationConnectionService:
    return IntegrationConnectionService(
        IntegrationConnectionRepository(session),
        credential_cipher=IntegrationCredentialCipher(settings.integration_key),
    )


def build_bug_service(session: AsyncSession, settings) -> BugService:
    from testing_agent.services.stored_file import StoredFileService

    return BugService(BugRepository(session), files=StoredFileService(session, settings.s3))


def get_bug_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BugService:
    return build_bug_service(session, settings)


def build_integration_bug_service(session: AsyncSession, settings: Settings):
    from testing_agent.repositories.integration_job import IntegrationJobRepository
    from testing_agent.services.bug_zentao_push import BugZentaoPushService
    from testing_agent.services.integration_authorization import IntegrationAuthorization
    from testing_agent.services.integration_bug import IntegrationBugService

    pushes = BugZentaoPushService(
        build_bug_service(session, settings), get_integration_connection_service(session, settings)
    )
    return IntegrationBugService(
        IntegrationJobRepository(session),
        pushes,
        IntegrationAuthorization(session, IntegrationCredentialCipher(settings.integration_key)),
        settings,
    )


def get_integration_bug_service(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return build_integration_bug_service(session, settings)


def get_shared_service(
    connections: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    from testing_agent.services.shared_service import SharedServiceService

    return SharedServiceService(connections)
