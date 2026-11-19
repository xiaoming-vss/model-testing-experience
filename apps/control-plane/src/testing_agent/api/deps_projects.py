from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.api.deps_common import get_file_service
from testing_agent.api.deps_integration import get_integration_connection_service
from testing_agent.core.config import Settings, get_settings
from testing_agent.db.session import get_session
from testing_agent.repositories.integration_connection import IntegrationConnectionRepository
from testing_agent.repositories.project import ProjectRepository
from testing_agent.repositories.project_skill_space import ProjectSkillSpaceRepository
from testing_agent.repositories.requirement import RequirementRepository
from testing_agent.repositories.requirement_software_repository import (
    RequirementSoftwareRepositoryRepository,
)
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.repositories.software_repository import SoftwareRepositoryRepository
from testing_agent.repositories.sprint import SprintRepository
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.baseline_resolution import BaselineResolutionService
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.project import ProjectService
from testing_agent.services.project_skill_space import ProjectSkillSpaceService
from testing_agent.services.requirement import RequirementService
from testing_agent.services.requirement_software_repository import (
    RequirementSoftwareRepositoryService,
)
from testing_agent.services.resource_binding import ResourceBindingService
from testing_agent.services.software_repository import SoftwareRepositoryService
from testing_agent.services.sprint import SprintService
from testing_agent.services.sprint_code_overview import SprintCodeOverviewService
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService
from testing_agent.services.zentao_mcp import ZentaoMcpResources


def get_project_service(session: AsyncSession = Depends(get_session)) -> ProjectService:
    return ProjectService(ProjectRepository(session))


def build_project_service(session: AsyncSession) -> ProjectService:
    return ProjectService(ProjectRepository(session))


def get_sprint_service(session: AsyncSession = Depends(get_session)) -> SprintService:
    return SprintService(SprintRepository(session), build_project_service(session))


def build_sprint_service(session: AsyncSession) -> SprintService:
    return SprintService(SprintRepository(session), build_project_service(session))


def get_requirement_service(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
) -> RequirementService:
    from testing_agent.services.requirement_generation_defaults import add_default_generation_tasks
    from testing_agent.services.stored_file import StoredFileService

    return RequirementService(
        RequirementRepository(session),
        build_sprint_service(session),
        StoredFileService(session, settings.s3),
        initialize_generation=lambda requirement, project_id, user_id: add_default_generation_tasks(
            session, requirement, project_id, user_id
        ),
    )


def get_software_repository_service(
    session: AsyncSession = Depends(get_session),
    connections: IntegrationConnectionService = Depends(get_integration_connection_service),
) -> SoftwareRepositoryService:
    return SoftwareRepositoryService(
        SoftwareRepositoryRepository(session),
        connections,
    )


def get_requirement_software_repository_service(
    session: AsyncSession = Depends(get_session),
    connections: IntegrationConnectionService = Depends(get_integration_connection_service),
) -> RequirementSoftwareRepositoryService:
    return RequirementSoftwareRepositoryService(
        RequirementSoftwareRepositoryRepository(session),
        SoftwareRepositoryRepository(session),
        connections,
    )


def get_resource_binding_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ResourceBindingService:
    return ResourceBindingService(
        ResourceBindingRepository(session),
        IntegrationConnectionService(
            IntegrationConnectionRepository(session),
            ZentaoMcpResources(),
            credential_cipher=IntegrationCredentialCipher(settings.integration_key),
        ),
        ZentaoMcpResources(),
    )


def get_sprint_code_overview_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SprintCodeOverviewService:
    credential_cipher = IntegrationCredentialCipher(settings.integration_key)
    integration_connection_service = IntegrationConnectionService(
        IntegrationConnectionRepository(session),
        credential_cipher=credential_cipher,
    )
    return SprintCodeOverviewService(
        build_sprint_service(session),
        BaselineResolutionService(RequirementSoftwareRepositoryRepository(session)),
        integration_connection_service,
        credential_cipher,
    )


def get_project_skill_space_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProjectSkillSpaceService:
    return ProjectSkillSpaceService(
        ProjectSkillSpaceRepository(session), get_file_service(session, settings)
    )


def get_sprint_daily_metrics_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SprintDailyMetricsService:
    return SprintDailyMetricsService(SprintDailyMetricsRepository(session))
