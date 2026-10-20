"""Assemble real generation capabilities for tests with explicit fake dependencies.

This preparation object contains capabilities, not delegated business methods.
Tests call the same command/query/workflow interfaces used by production handlers.
"""

from types import SimpleNamespace

from testing_agent.api import deps
from testing_agent.core.sid import new_id
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.repositories.requirement_design import RequirementDesignRepository
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.ai_candidate_review import GenerationCandidateReview
from testing_agent.services.ai_execution.writer import SqlExecutionWriter
from testing_agent.services.ai_report import TestReportWorkflow
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_source_archive import SourceArchiveManager
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_access import GenerationImportContext
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.requirement_design import RequirementDesignService
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService


def generation_services(
    repository,
    sprint_daily_metrics_service=None,
    files=None,
    code_risk_analysis_service=None,
    execution_writer=None,
    *,
    deletion=None,
    source_archive_repository=None,
    id_factory=None,
):
    execution = execution_writer or SqlExecutionWriter()
    access = GenerationAccess(repository)
    archive_repository = source_archive_repository
    if archive_repository is None:
        archive_repository = (
            repository
            if hasattr(repository, "get_source_archive") or not hasattr(repository, "session")
            else AiGenerateTaskSourceArchiveRepository(repository.session)
        )
    metrics = sprint_daily_metrics_service
    if metrics is None and hasattr(repository, "session"):
        metrics = SprintDailyMetricsService(SprintDailyMetricsRepository(repository.session))
    identifiers = id_factory or (lambda: new_id())
    commands = GenerationTaskCommands(
        repository, archive_repository, access, deletion=deletion, id_factory=identifiers
    )
    launcher = GenerationRunLauncher(
        repository=repository,
        source_archive_repository=archive_repository,
        access=access,
        execution=execution,
        sprint_daily_metrics_service=metrics,
        code_risk_analysis_service=code_risk_analysis_service,
        id_factory=identifiers,
    )
    bundle = SimpleNamespace(
        repository=repository,
        execution=execution,
        access=access,
        commands=commands,
        source_archive_repository=archive_repository,
        files=files,
        queries=GenerationQueries(repository, archive_repository, access),
        launcher=launcher,
        stages=GenerationStageWorkflow(
            repository=repository,
            owned_run=access.owned_run,
            execution_writer=execution,
            id_factory=identifiers,
        ),
        reports=TestReportWorkflow(
            repository=repository,
            sprint_daily_metrics_service=metrics,
            ensure_project_access=access.ensure_project_access,
            owned_run=access.owned_run,
            execution_writer=execution,
            id_factory=identifiers,
        ),
        archives=SourceArchiveManager(
            source_archive_repository=archive_repository,
            files=files,
            owned_task=access.owned_task,
            id_factory=identifiers,
        ),
        review=GenerationCandidateReview(repository, access.owned_run, execution),
        api_importer=ApiCandidateImporter(
            repository=repository,
            owned_run=access.owned_run,
            ensure_collection_access=access.ensure_collection_access,
            execution_writer=execution,
            id_factory=identifiers,
        ),
        imports=GenerationImportContext(repository, access, execution),
    )
    if hasattr(repository, "session"):
        bundle.design = RequirementDesignService(
            RequirementDesignRepository(repository.session),
            repository,
            archive_repository,
            access,
            commands,
            launcher,
        )
    return bundle


def install_generation_services(app, services):
    def provide(capability):
        def dependency():
            return capability

        return dependency

    for dependency, capability in (
        (deps.get_generation_access, services.access),
        (deps.get_generation_queries, services.queries),
        (deps.get_generation_task_commands, services.commands),
        (deps.get_generation_launcher, services.launcher),
        (deps.get_generation_stages, services.stages),
        (deps.get_generation_reports, services.reports),
        (deps.get_generation_archives, services.archives),
        (deps.get_generation_review, services.review),
        (deps.get_generation_api_importer, services.api_importer),
        (deps.get_generation_import_context, services.imports),
    ):
        app.dependency_overrides[dependency] = provide(capability)
    if hasattr(services, "design"):
        app.dependency_overrides[deps.get_requirement_design_service] = lambda: services.design
