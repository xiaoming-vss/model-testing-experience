from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from testing_agent.services.project_access import ProjectAction
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion

if TYPE_CHECKING:
    from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService

from testing_agent.core.enums import ReviewStatus, RunStatus
from testing_agent.core.errors import (
    ErrAiGenerateTaskRunReviewed,
    ErrBadRequest,
    ErrNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.domain.ai_tasks import (
    DEFAULT_FUNCTION_CASE_MODULE as DEFAULT_FUNCTION_CASE_MODULE,
)
from testing_agent.domain.ai_tasks import (
    FUNCTION_CASE_NEXT_STAGE as FUNCTION_CASE_NEXT_STAGE,
)
from testing_agent.domain.ai_tasks import (
    FUNCTION_CASE_RELATION_DISPATCH_STATUSES as FUNCTION_CASE_RELATION_DISPATCH_STATUSES,
)
from testing_agent.domain.ai_tasks import (
    FUNCTION_CASE_RELATION_STAGE as FUNCTION_CASE_RELATION_STAGE,
)
from testing_agent.domain.ai_tasks import (
    FUNCTION_CASE_REVIEW_READY_STATUSES as FUNCTION_CASE_REVIEW_READY_STATUSES,
)
from testing_agent.domain.ai_tasks import (
    FUNCTION_CASE_REVIEWABLE_STAGES as FUNCTION_CASE_REVIEWABLE_STAGES,
)
from testing_agent.domain.ai_tasks import (
    REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES as REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES,
)
from testing_agent.domain.ai_tasks import (
    REQUIREMENT_ANALYSIS_FINAL_STAGE as REQUIREMENT_ANALYSIS_FINAL_STAGE,
)
from testing_agent.domain.ai_tasks import (
    REQUIREMENT_ANALYSIS_INITIAL_STAGE as REQUIREMENT_ANALYSIS_INITIAL_STAGE,
)
from testing_agent.domain.ai_tasks import (
    REQUIREMENT_ANALYSIS_NEXT_STAGE as REQUIREMENT_ANALYSIS_NEXT_STAGE,
)
from testing_agent.domain.ai_tasks import (
    REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES as REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES,
)
from testing_agent.domain.ai_tasks import (
    REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES as REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES,
)
from testing_agent.domain.ai_tasks import (
    REVISION_INSTRUCTION_FIELD as REVISION_INSTRUCTION_FIELD,
)
from testing_agent.domain.ai_tasks import (
    next_function_case_stage as next_function_case_stage,
)
from testing_agent.domain.ai_tasks import (
    next_requirement_analysis_stage as next_requirement_analysis_stage,
)
from testing_agent.domain.ai_tasks import task_type_for as task_type_for
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.ai_execution.writer import ExecutionWriter, SqlExecutionWriter
from testing_agent.services.ai_report import TestReportWorkflow
from testing_agent.services.ai_report import (
    build_test_report_run_snapshot as build_test_report_run_snapshot,
)
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_source_archive import (
    MAX_SOURCE_ARCHIVE_BYTES as MAX_SOURCE_ARCHIVE_BYTES,
)
from testing_agent.services.ai_source_archive import (
    MAX_SOURCE_ARCHIVE_FILES as MAX_SOURCE_ARCHIVE_FILES,
)
from testing_agent.services.ai_source_archive import (
    MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES as MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES,
)
from testing_agent.services.ai_source_archive import SourceArchiveManager
from testing_agent.services.ai_source_archive import (
    validate_source_archive as validate_source_archive,
)
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_output import (
    build_generate_run_snapshot as build_generate_run_snapshot,
)
from testing_agent.services.ai_task_output import dump_run as dump_run
from testing_agent.services.ai_task_output import dump_source_archive as dump_source_archive
from testing_agent.services.ai_task_output import dump_task as dump_task
from testing_agent.services.ai_task_output import first_present as first_present
from testing_agent.services.ai_task_output import generated_api_cases as generated_api_cases
from testing_agent.services.ai_task_output import (
    generated_function_cases as generated_function_cases,
)
from testing_agent.services.ai_task_output import (
    generated_function_suites as generated_function_suites,
)
from testing_agent.services.ai_task_output import generated_payload as generated_payload
from testing_agent.services.ai_task_output import import_lines as import_lines
from testing_agent.services.ai_task_output import is_ai_run_reviewable as is_ai_run_reviewable
from testing_agent.services.ai_task_output import normalize_config_json as normalize_config_json
from testing_agent.services.ai_task_output import (
    normalize_function_case_module as normalize_function_case_module,
)
from testing_agent.services.ai_task_output import (
    normalize_function_stage_config as normalize_function_stage_config,
)
from testing_agent.services.ai_task_output import (
    normalize_generated_function_case as normalize_generated_function_case,
)
from testing_agent.services.ai_task_output import (
    requirement_analysis_import_content as requirement_analysis_import_content,
)
from testing_agent.services.ai_task_output import (
    requirement_document_download_url as requirement_document_download_url,
)
from testing_agent.services.ai_task_output import (
    requirement_source_content as requirement_source_content,
)
from testing_agent.services.ai_task_output import (
    validate_function_candidate_cases as validate_function_candidate_cases,
)
from testing_agent.services.ai_task_output import (
    validate_ui_candidate_cases as validate_ui_candidate_cases,
)
from testing_agent.services.ai_task_output import (
    worker_requirement_document_download_url as worker_requirement_document_download_url,
)
from testing_agent.services.ai_task_output import (
    worker_source_archive_download_url as worker_source_archive_download_url,
)
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.api_import_payload import bool_value as bool_value
from testing_agent.services.api_import_payload import validate_api_collection_import_payload
from testing_agent.services.import_payload import parse_import_payload
from testing_agent.services.requirement import dump_requirement
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService


class AiGenerateTaskService:
    def __init__(
        self,
        repository: AiGenerateTaskRepository,
        sprint_daily_metrics_service: SprintDailyMetricsService | None = None,
        files=None,
        code_risk_analysis_service: CodeRiskAnalysisService | None = None,
        execution_writer: ExecutionWriter | None = None,
        *,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.deletion = deletion or SqlResourceDeletion()
        self.repository = repository
        self.execution = execution_writer or SqlExecutionWriter()
        self.code_risk_analysis_service = code_risk_analysis_service
        self.source_archive_repository: Any
        if hasattr(repository, "get_source_archive"):
            self.source_archive_repository = repository
        elif hasattr(repository, "session"):
            self.source_archive_repository = AiGenerateTaskSourceArchiveRepository(
                repository.session
            )
        else:
            self.source_archive_repository = repository
        self.files = files
        if sprint_daily_metrics_service is None and hasattr(repository, "session"):
            sprint_daily_metrics_service = SprintDailyMetricsService(
                SprintDailyMetricsRepository(repository.session)
            )
        self.sprint_daily_metrics_service = sprint_daily_metrics_service

    async def ensure_project_access(
        self, user_id: str, project_id: str, *, action: ProjectAction = "read"
    ) -> None:
        return await GenerationAccess(self.repository).ensure_project_access(
            user_id, project_id, action=action
        )

    async def ensure_sprint_access(
        self, user_id: str, sprint_id: str, *, action: ProjectAction = "read"
    ) -> None:
        return await GenerationAccess(self.repository).ensure_sprint_access(
            user_id, sprint_id, action=action
        )

    async def ensure_requirement_access(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> None:
        return await GenerationAccess(self.repository).ensure_requirement_access(
            user_id, requirement_id, action=action
        )

    async def ensure_collection_access(
        self, user_id: str, collection_id: str, *, action: ProjectAction = "read"
    ) -> None:
        return await GenerationAccess(self.repository).ensure_collection_access(
            user_id, collection_id, action=action
        )

    async def validate_task_scope(self, task, resources=None) -> None:
        return await GenerationAccess(self.repository).validate_task_scope(task, resources)

    async def owned_task(
        self,
        user_id: str,
        task_id: str,
        kind: str | None = None,
        *,
        action: ProjectAction = "read",
        current_read: bool = False,
    ) -> AiGenerateTask:
        return await GenerationAccess(self.repository).owned_task(
            user_id, task_id, kind, action=action, current_read=current_read
        )

    async def owned_run(
        self, user_id: str, run_id: str, kind: str | None = None, *, action: ProjectAction = "read"
    ) -> AiGenerateTaskRun:
        return await GenerationAccess(self.repository).owned_run(
            user_id, run_id, kind, action=action
        )

    async def create(
        self,
        kind: str,
        project_id: str,
        body: dict[str, Any],
        user_id: str,
        *,
        task_id: str | None = None,
    ) -> dict:
        return await GenerationTaskCommands(
            self.repository,
            self.source_archive_repository,
            GenerationAccess(self.repository),
            deletion=self.deletion,
            id_factory=new_id,
        ).create(kind, project_id, body, user_id, task_id=task_id)

    async def list(self, kind: str, project_id: str, user_id: str) -> dict[str, Any]:
        return await GenerationQueries(
            self.repository, self.source_archive_repository, GenerationAccess(self.repository)
        ).list(kind, project_id, user_id)

    async def get(self, kind: str, task_id: str, user_id: str) -> dict:
        return await GenerationQueries(
            self.repository, self.source_archive_repository, GenerationAccess(self.repository)
        ).get(kind, task_id, user_id)

    async def upload_source_archive(
        self, task_id: str, file_id: str, user_id: str
    ) -> dict[str, Any]:
        workflow = SourceArchiveManager(
            source_archive_repository=self.source_archive_repository,
            files=self.files,
            owned_task=self.owned_task,
            id_factory=new_id,
        )
        return await workflow.upload_source_archive(task_id, file_id, user_id)

    async def update(
        self,
        kind: str,
        task_id: str,
        body: dict[str, Any],
        user_id: str,
        *,
        current_read: bool = False,
    ) -> dict:
        return await GenerationTaskCommands(
            self.repository,
            self.source_archive_repository,
            GenerationAccess(self.repository),
            deletion=self.deletion,
            id_factory=new_id,
        ).update(kind, task_id, body, user_id, current_read=current_read)

    async def delete(self, kind: str, task_id: str, user_id: str) -> dict:
        return await GenerationTaskCommands(
            self.repository,
            self.source_archive_repository,
            GenerationAccess(self.repository),
            deletion=self.deletion,
            id_factory=new_id,
        ).delete(kind, task_id, user_id)

    async def delete_run(self, kind: str, run_id: str, user_id: str) -> dict:
        return await GenerationTaskCommands(
            self.repository,
            self.source_archive_repository,
            GenerationAccess(self.repository),
            deletion=self.deletion,
            id_factory=new_id,
        ).delete_run(kind, run_id, user_id)

    async def test_report_task_for_run(
        self, project_id: str, body: dict[str, Any], user_id: str
    ) -> AiGenerateTask:
        workflow = TestReportWorkflow(
            repository=self.repository,
            sprint_daily_metrics_service=self.sprint_daily_metrics_service,
            ensure_project_access=self.ensure_project_access,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.test_report_task_for_run(project_id, body, user_id)

    async def run_test_report(
        self, project_id: str, body: dict[str, Any] | None, user_id: str
    ) -> dict:
        workflow = TestReportWorkflow(
            repository=self.repository,
            sprint_daily_metrics_service=self.sprint_daily_metrics_service,
            ensure_project_access=self.ensure_project_access,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.run_test_report(project_id, body, user_id)

    async def list_test_report_runs(
        self, project_id: str, sprint_id: str, user_id: str
    ) -> dict[str, Any]:
        workflow = TestReportWorkflow(
            repository=self.repository,
            sprint_daily_metrics_service=self.sprint_daily_metrics_service,
            ensure_project_access=self.ensure_project_access,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.list_test_report_runs(project_id, sprint_id, user_id)

    async def export_test_report_pdf(self, run_id: str, user_id: str) -> tuple[bytes, str]:
        workflow = TestReportWorkflow(
            repository=self.repository,
            sprint_daily_metrics_service=self.sprint_daily_metrics_service,
            ensure_project_access=self.ensure_project_access,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.export_test_report_pdf(run_id, user_id)

    async def run(
        self,
        kind: str,
        task_id: str,
        body: dict[str, Any] | None,
        user_id: str,
        *,
        request_id: str | None = None,
    ) -> dict:
        launcher = GenerationRunLauncher(
            repository=self.repository,
            source_archive_repository=self.source_archive_repository,
            access=self,
            execution=self.execution,
            sprint_daily_metrics_service=self.sprint_daily_metrics_service,
            code_risk_analysis_service=self.code_risk_analysis_service,
            id_factory=new_id,
        )
        return await launcher.launch(kind, task_id, body, user_id, request_id=request_id)

    async def update_result(
        self, kind: str, run_id: str, result_yaml: str, user_id: str
    ) -> dict[str, Any]:
        if kind not in {"api", "function", "ui"}:
            raise ErrBadRequest()
        run = await self.owned_run(user_id, run_id, kind, action="write")
        if run.status != RunStatus.SUCCESS.value or run.review_status != ReviewStatus.PENDING.value:
            raise ErrBadRequest()
        if kind == "api":
            payload = parse_import_payload(result_yaml)
            await validate_api_collection_import_payload(
                self.repository, "", payload, check_existing=False
            )
        elif kind == "function":
            cases = generated_function_cases(SimpleNamespace(result_yaml=result_yaml))
            if not cases:
                raise ErrBadRequest()
            validate_function_candidate_cases(cases)
        else:
            validate_ui_candidate_cases(result_yaml)
        run.result_yaml = result_yaml
        await self.execution.save(
            self.repository.session, run, intent=ExecutionIntent(actor_id=user_id)
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def import_api_run(
        self,
        run_id: str,
        collection_id: str,
        confirm_overwrite: bool,
        user_id: str,
    ) -> dict[str, Any]:
        workflow = ApiCandidateImporter(
            repository=self.repository,
            owned_run=self.owned_run,
            ensure_collection_access=self.ensure_collection_access,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.import_api_run(run_id, collection_id, confirm_overwrite, user_id)

    async def import_ui_run(
        self,
        run_id: str,
        suite_id: str,
        confirm_overwrite: bool,
        user_id: str,
    ) -> dict[str, Any]:
        from testing_agent.services.ui_generate_import import import_ui_run

        return await import_ui_run(self, run_id, suite_id, confirm_overwrite, user_id)

    async def list_run_summaries(
        self,
        kind: str,
        task_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        pipeline_filter: str = "all",
    ) -> dict[str, Any]:
        return await GenerationQueries(
            self.repository, self.source_archive_repository, GenerationAccess(self.repository)
        ).list_run_summaries(kind, task_id, user_id, page, page_size, pipeline_filter)

    async def list_test_report_run_summaries(
        self, project_id: str, sprint_id: str, user_id: str, page: int = 1, page_size: int = 20
    ):
        return await GenerationQueries(
            self.repository, self.source_archive_repository, GenerationAccess(self.repository)
        ).list_test_report_run_summaries(project_id, sprint_id, user_id, page, page_size)

    async def list_runs(self, kind: str, task_id: str, user_id: str) -> dict[str, Any]:
        return await GenerationQueries(
            self.repository, self.source_archive_repository, GenerationAccess(self.repository)
        ).list_runs(kind, task_id, user_id)

    async def import_requirement_analysis_run(self, run_id: str, user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, "requirement_analysis", action="execute")
        if (
            run.status != RunStatus.SUCCESS.value
            or run.review_status != ReviewStatus.APPROVED.value
        ):
            raise ErrBadRequest()
        requirement = await self.repository.get_requirement(run.requirement_id)
        if requirement is None:
            raise ErrNotFound()
        await self.ensure_requirement_access(user_id, requirement.requirement_id, action="execute")
        requirement.document_content = requirement_analysis_import_content(run)
        await self.execution.save(
            self.repository.session, run, intent=ExecutionIntent(actor_id=user_id)
        )
        await self.repository.commit()
        await self.repository.refresh(requirement)
        return dump_requirement(requirement)

    async def review(self, kind: str, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, kind, action="review")
        if not is_ai_run_reviewable(run.status):
            raise ErrBadRequest()
        if run.review_status != ReviewStatus.PENDING.value:
            raise ErrAiGenerateTaskRunReviewed()
        action = str(
            body.get("action") or body.get("reviewStatus") or body.get("status") or "approve"
        )
        if action == "approved":
            action = "approve"
        if action == "rejected":
            action = "reject"
        if kind in {"api", "function", "ui"}:
            if action == "approve":
                if run.status != RunStatus.SUCCESS.value:
                    raise ErrBadRequest()
                if kind == "api":
                    await validate_api_collection_import_payload(
                        self.repository, "", generated_payload(run)
                    )
                elif kind == "function":
                    cases = generated_function_cases(run)
                    if not cases:
                        raise ErrBadRequest()
                    validate_function_candidate_cases(cases)
                else:
                    validate_ui_candidate_cases(run.result_yaml)
                run.review_status = ReviewStatus.APPROVED.value
            elif action == "reject":
                run.review_status = ReviewStatus.REJECTED.value
            else:
                raise ErrBadRequest()
            run.review_comment = str(body.get("reviewComment") or body.get("comment") or "")
            run.reviewer_user_id = user_id
            run.reviewed_at = datetime.now(UTC)
            await self.execution.save(
                self.repository.session, run, intent=ExecutionIntent(actor_id=user_id)
            )
            await self.repository.commit()
            await self.repository.refresh(run)
            return dump_run(run)
        raise ErrBadRequest()

    async def save_stage_output(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.save_stage_output(run_id, body, user_id)

    async def save_requirement_analysis_stage_output(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.save_requirement_analysis_stage_output(run_id, body, user_id)

    async def review_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.review_requirement_analysis_stage(run_id, body, user_id)

    async def revise_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.revise_requirement_analysis_stage(run_id, body, user_id)

    async def revise_function_case_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.revise_function_case_stage(run_id, body, user_id)

    async def review_stage(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.review_stage(run_id, body, user_id)

    async def retry_stage(
        self,
        run_id: str,
        body: dict[str, Any] | None,
        user_id: str,
        *,
        kind: str = "function",
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.retry_stage(run_id, body, user_id, kind=kind)

    async def generate_relation_analysis(
        self, run_id: str, body: dict[str, Any] | None, user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository,
            owned_run=self.owned_run,
            id_factory=new_id,
            execution_writer=self.execution,
        )
        return await workflow.generate_relation_analysis(run_id, body, user_id)
