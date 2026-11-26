from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.api.deps_common import get_file_service
from testing_agent.core.config import Settings, get_settings
from testing_agent.db.session import get_session
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.repositories.integration_connection import IntegrationConnectionRepository
from testing_agent.repositories.requirement_design import RequirementDesignRepository
from testing_agent.repositories.requirement_software_repository import (
    RequirementSoftwareRepositoryRepository,
)
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.services.ai_report import TestReportWorkflow
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_task_access import GenerationImportContext
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.repository_profile import RepositoryProfileService
from testing_agent.services.requirement_design import RequirementDesignService
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService
from testing_agent.services.ui_generation_source import UiGenerationSourceService
from testing_agent.services.worker_task import WorkerTaskService


def get_generation_access(
    session: AsyncSession = Depends(get_session),
) -> GenerationAccess:
    return GenerationAccess(AiGenerateTaskRepository(session))


def get_generation_queries(
    access: GenerationAccess = Depends(get_generation_access),
) -> GenerationQueries:
    return GenerationQueries(access.repository, access)


def get_generation_task_commands(
    access: GenerationAccess = Depends(get_generation_access),
) -> GenerationTaskCommands:
    return GenerationTaskCommands(access.repository, access)


def get_generation_metrics(
    access: GenerationAccess = Depends(get_generation_access),
) -> SprintDailyMetricsService:
    return SprintDailyMetricsService(SprintDailyMetricsRepository(access.repository.session))


def get_generation_launcher(
    access: GenerationAccess = Depends(get_generation_access),
    metrics: SprintDailyMetricsService = Depends(get_generation_metrics),
    settings: Settings = Depends(get_settings),
    files=Depends(get_file_service),
) -> GenerationRunLauncher:
    session = access.repository.session
    cipher = IntegrationCredentialCipher(settings.integration_key)
    connections = IntegrationConnectionService(
        IntegrationConnectionRepository(session), credential_cipher=cipher
    )
    requirements = RequirementSoftwareRepositoryRepository(session)
    return GenerationRunLauncher(
        repository=access.repository,
        access=access,
        sprint_daily_metrics_service=metrics,
        code_risk_analysis_service=CodeRiskAnalysisService(
            access.repository,
            requirements,
            connections,
            cipher,
        ),
        repository_profile_service=RepositoryProfileService(
            access.repository,
            requirements,
            connections,
            cipher,
        ),
        files=files,
    )


def get_generation_reports(
    access: GenerationAccess = Depends(get_generation_access),
    metrics: SprintDailyMetricsService = Depends(get_generation_metrics),
) -> TestReportWorkflow:
    return TestReportWorkflow(
        repository=access.repository,
        sprint_daily_metrics_service=metrics,
        ensure_project_access=access.ensure_project_access,
    )


def get_generation_api_importer(
    access: GenerationAccess = Depends(get_generation_access),
) -> ApiCandidateImporter:
    return ApiCandidateImporter(
        repository=access.repository,
        ensure_collection_access=access.ensure_collection_access,
    )


def get_generation_import_context(
    access: GenerationAccess = Depends(get_generation_access),
) -> GenerationImportContext:
    return GenerationImportContext(access.repository, access)


def get_requirement_design_service(
    access: GenerationAccess = Depends(get_generation_access),
    commands: GenerationTaskCommands = Depends(get_generation_task_commands),
) -> RequirementDesignService:
    return RequirementDesignService(
        RequirementDesignRepository(access.repository.session),
        access.repository,
        access,
        commands,
    )


def get_worker_task_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WorkerTaskService:
    return WorkerTaskService(
        WorkerTaskRepository(session),
        credential_cipher=IntegrationCredentialCipher(settings.integration_key),
    )


def get_ui_worker_artifact_service(
    tasks: WorkerTaskService = Depends(get_worker_task_service),
    files=Depends(get_file_service),
):
    from testing_agent.services.ui_worker_artifacts import UiWorkerArtifactService

    return UiWorkerArtifactService(tasks, files)


def get_ui_generation_sources(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UiGenerationSourceService:
    cipher = IntegrationCredentialCipher(settings.integration_key)
    return UiGenerationSourceService(
        session,
        integration_connection_service=IntegrationConnectionService(
            IntegrationConnectionRepository(session), credential_cipher=cipher
        ),
        credential_cipher=cipher,
    )


def get_generation_chain(
    access: GenerationAccess = Depends(get_generation_access),
    files=Depends(get_file_service),
    imports: GenerationImportContext = Depends(get_generation_import_context),
    api_importer: ApiCandidateImporter = Depends(get_generation_api_importer),
    ui_sources: UiGenerationSourceService = Depends(get_ui_generation_sources),
) -> GenerationChainService:
    return GenerationChainService(
        repository=GenerationChainRepository(access.repository.session),
        tasks=access.repository,
        access=access,
        files=files,
        imports=imports,
        api_importer=api_importer,
        ui_sources=ui_sources,
    )
