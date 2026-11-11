"""Assemble production generation capabilities for tests with explicit fake dependencies.

This preparation object contains capabilities, not delegated business methods.
Tests call the same command/query/workflow interfaces used by production handlers.
"""

from types import SimpleNamespace

from testing_agent.core.sid import new_id
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.repositories.requirement_design import RequirementDesignRepository
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.ai_candidate_review import GenerationCandidateReview
from testing_agent.services.ai_report import TestReportWorkflow
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_access import GenerationImportContext
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.requirement_design import RequirementDesignService
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService
from testing_agent.services.ui_generation_source import UiGenerationSourceService
from testing_agent.services.ui_generation_workflow import UiGenerationWorkflow

_deps = None


def _dependencies():
    global _deps
    if _deps is None:
        from testing_agent.api import deps as module

        _deps = module
    return _deps


def generation_services(
    repository,
    sprint_daily_metrics_service=None,
    files=None,
    code_risk_analysis_service=None,
    repository_profile_service=None,
    execution_writer=None,
    *,
    deletion=None,
    id_factory=None,
):
    access = GenerationAccess(repository)
    metrics = sprint_daily_metrics_service
    if metrics is None and hasattr(repository, "session"):
        metrics = SprintDailyMetricsService(SprintDailyMetricsRepository(repository.session))
    identifiers = id_factory or (lambda: new_id())
    commands = GenerationTaskCommands(repository, access, deletion=deletion, id_factory=identifiers)
    launcher = GenerationRunLauncher(
        repository=repository,
        access=access,
        sprint_daily_metrics_service=metrics,
        code_risk_analysis_service=code_risk_analysis_service,
        repository_profile_service=repository_profile_service,
        id_factory=identifiers,
    )
    stages_workflow = GenerationStageWorkflow(
        repository=repository,
        owned_run=access.owned_run,
        id_factory=identifiers,
        files=files,
        access=access,
    )
    ui_stages_workflow = UiGenerationWorkflow(
        repository=repository,
        owned_run=access.owned_run,
        id_factory=identifiers,
        files=files,
    )
    review_service = GenerationCandidateReview(repository, access.owned_run)
    bundle = SimpleNamespace(
        repository=repository,
        access=access,
        commands=commands,
        files=files,
        queries=GenerationQueries(repository, access),
        launcher=launcher,
        stages=stages_workflow,
        ui_stages=ui_stages_workflow,
        reports=TestReportWorkflow(
            repository=repository,
            sprint_daily_metrics_service=metrics,
            ensure_project_access=access.ensure_project_access,
            owned_run=access.owned_run,
            id_factory=identifiers,
        ),
        review=review_service,
        api_importer=ApiCandidateImporter(
            repository=repository,
            owned_run=access.owned_run,
            ensure_collection_access=access.ensure_collection_access,
            id_factory=identifiers,
        ),
        imports=GenerationImportContext(repository, access),
    )
    if hasattr(repository, "session"):
        ui_sources = UiGenerationSourceService(
            repository.session,
            binding_repository=ResourceBindingRepository(repository.session),
            integration_connection_service=SimpleNamespace(),
            credential_cipher=None,
        )
        bundle.chain = GenerationChainService(
            repository=GenerationChainRepository(repository.session),
            tasks=repository,
            access=access,
            files=files,
            imports=bundle.imports,
            api_importer=bundle.api_importer,
            ui_sources=ui_sources,
            id_factory=identifiers,
        )
        bundle.design = RequirementDesignService(
            RequirementDesignRepository(repository.session),
            repository,
            access,
            commands,
        )
    return bundle


def install_generation_services(app, services):
    deps = _dependencies()

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
        (deps.get_ui_generation_stages, services.ui_stages),
        (deps.get_generation_reports, services.reports),
        (deps.get_generation_review, services.review),
        (deps.get_generation_api_importer, services.api_importer),
        (deps.get_generation_import_context, services.imports),
    ):
        app.dependency_overrides[dependency] = provide(capability)
    if hasattr(services, "design"):
        app.dependency_overrides[deps.get_requirement_design_service] = lambda: services.design
    if hasattr(services, "chain"):
        app.dependency_overrides[deps.get_generation_chain] = lambda: services.chain
