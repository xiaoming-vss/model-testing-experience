from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.project_access import ProjectAction, require_project_access

if TYPE_CHECKING:
    from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService

from testing_agent.core.enums import RUN_ACTIVE_STATUSES, ReviewStatus, RunStatus, StageStatus
from testing_agent.core.errors import (
    ErrAiGenerateTaskRunReviewed,
    ErrAiGenerateTaskRunRunning,
    ErrBadRequest,
    ErrForbidden,
    ErrNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.ai_report import TestReportWorkflow
from testing_agent.services.ai_report import (
    build_test_report_run_snapshot as build_test_report_run_snapshot,
)
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
from testing_agent.services.ai_task_contracts import (
    DEFAULT_FUNCTION_CASE_MODULE as DEFAULT_FUNCTION_CASE_MODULE,
)
from testing_agent.services.ai_task_contracts import (
    FUNCTION_CASE_NEXT_STAGE as FUNCTION_CASE_NEXT_STAGE,
)
from testing_agent.services.ai_task_contracts import (
    FUNCTION_CASE_RELATION_DISPATCH_STATUSES as FUNCTION_CASE_RELATION_DISPATCH_STATUSES,
)
from testing_agent.services.ai_task_contracts import (
    FUNCTION_CASE_RELATION_STAGE as FUNCTION_CASE_RELATION_STAGE,
)
from testing_agent.services.ai_task_contracts import (
    FUNCTION_CASE_REVIEW_READY_STATUSES as FUNCTION_CASE_REVIEW_READY_STATUSES,
)
from testing_agent.services.ai_task_contracts import (
    FUNCTION_CASE_REVIEWABLE_STAGES as FUNCTION_CASE_REVIEWABLE_STAGES,
)
from testing_agent.services.ai_task_contracts import (
    REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES as REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES,
)
from testing_agent.services.ai_task_contracts import (
    REQUIREMENT_ANALYSIS_FINAL_STAGE as REQUIREMENT_ANALYSIS_FINAL_STAGE,
)
from testing_agent.services.ai_task_contracts import (
    REQUIREMENT_ANALYSIS_INITIAL_STAGE as REQUIREMENT_ANALYSIS_INITIAL_STAGE,
)
from testing_agent.services.ai_task_contracts import (
    REQUIREMENT_ANALYSIS_NEXT_STAGE as REQUIREMENT_ANALYSIS_NEXT_STAGE,
)
from testing_agent.services.ai_task_contracts import (
    REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES as REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES,
)
from testing_agent.services.ai_task_contracts import (
    REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES as REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES,
)
from testing_agent.services.ai_task_contracts import (
    REVISION_INSTRUCTION_FIELD as REVISION_INSTRUCTION_FIELD,
)
from testing_agent.services.ai_task_contracts import (
    next_function_case_stage as next_function_case_stage,
)
from testing_agent.services.ai_task_contracts import (
    next_requirement_analysis_stage as next_requirement_analysis_stage,
)
from testing_agent.services.ai_task_contracts import task_type_for as task_type_for
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
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.api_import_payload import bool_value as bool_value
from testing_agent.services.api_import_payload import (
    parse_import_payload,
    validate_api_collection_import_payload,
)
from testing_agent.services.common import list_payload
from testing_agent.services.requirement import dump_requirement
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService


class AiGenerateTaskService:
    def __init__(
        self,
        repository: AiGenerateTaskRepository,
        sprint_daily_metrics_service: SprintDailyMetricsService | None = None,
        source_archive_storage_root: str | Path | None = None,
        code_risk_analysis_service: CodeRiskAnalysisService | None = None,
    ):
        self.repository = repository
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
        self.source_archive_storage_root = Path(
            source_archive_storage_root or "storage/ai-generate-task-sources"
        )
        if sprint_daily_metrics_service is None and hasattr(repository, "session"):
            sprint_daily_metrics_service = SprintDailyMetricsService(
                SprintDailyMetricsRepository(repository.session)
            )
        self.sprint_daily_metrics_service = sprint_daily_metrics_service

    async def ensure_project_access(
        self, user_id: str, project_id: str, *, action: ProjectAction = "read"
    ) -> None:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)

    async def ensure_sprint_access(
        self, user_id: str, sprint_id: str, *, action: ProjectAction = "read"
    ) -> None:
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None:
            raise ErrNotFound
        await self.ensure_project_access(user_id, sprint.project_id, action=action)

    async def ensure_requirement_access(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> None:
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound
        await self.ensure_sprint_access(user_id, requirement.sprint_id, action=action)

    async def ensure_collection_access(
        self, user_id: str, collection_id: str, *, action: ProjectAction = "read"
    ) -> None:
        collection = await self.repository.get_collection(collection_id)
        if collection is None:
            raise ErrNotFound
        await self.ensure_requirement_access(user_id, collection.requirement_id, action=action)

    async def owned_task(
        self, user_id: str, task_id: str, kind: str | None = None, *, action: ProjectAction = "read"
    ) -> AiGenerateTask:
        task = await self.repository.get_task(task_id)
        if task is None:
            raise ErrNotFound
        if kind and task.task_type != task_type_for(kind):
            raise ErrNotFound
        await self.ensure_project_access(user_id, task.project_id, action=action)
        return task

    async def owned_run(
        self, user_id: str, run_id: str, kind: str | None = None, *, action: ProjectAction = "read"
    ) -> AiGenerateTaskRun:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise ErrNotFound
        task = await self.owned_task(user_id, run.task_id, kind, action=action)
        if task.project_id != run.project_id:
            raise ErrForbidden
        run._actor = user_id
        return run

    async def create(self, kind: str, project_id: str, body: dict[str, Any], user_id: str) -> dict:
        await self.ensure_project_access(user_id, project_id, action="write")
        sprint_id = str(body.get("sprintId") or body.get("sprint_id") or "")
        requirement_id = str(body.get("requirementId") or body.get("requirement_id") or "")
        requirement = None
        if kind in {"ui", "requirement_analysis", "code_risk_analysis"}:
            if not requirement_id:
                raise ErrBadRequest
            requirement = await self.repository.get_requirement(requirement_id)
            if requirement is None:
                raise ErrNotFound
            sprint = await self.repository.get_sprint(requirement.sprint_id)
            if sprint is None or sprint.project_id != project_id:
                raise ErrNotFound
            sprint_id = requirement.sprint_id
        if kind == "test_report":
            if not sprint_id:
                raise ErrBadRequest
            sprint = await self.repository.get_sprint(sprint_id)
            if sprint is None or sprint.project_id != project_id:
                raise ErrNotFound
            existing = await self.repository.get_active_task_by_project_sprint_type(
                project_id, sprint_id, task_type_for(kind)
            )
            if existing is not None:
                raise ErrBadRequest
        if sprint_id:
            await self.ensure_sprint_access(user_id, sprint_id, action="write")
        if requirement_id:
            await self.ensure_requirement_access(user_id, requirement_id, action="write")
        task = AiGenerateTask(
            task_id=new_id(),
            task_type=task_type_for(kind),
            name=str(
                body.get("name")
                or (
                    f"{requirement.name} analysis"
                    if kind == "requirement_analysis" and requirement is not None
                    else (
                        f"{requirement.name} 代码风险分析"
                        if kind == "code_risk_analysis" and requirement is not None
                        else (
                            "test-report-generate-task"
                            if kind == "test_report"
                            else f"{kind}-case-generate-task"
                        )
                    )
                )
            ),
            project_id=project_id,
            sprint_id=sprint_id,
            requirement_id=requirement_id,
            creator_user_id=user_id,
            source_type=str(
                "source_archive"
                if kind == "ui"
                else requirement.document_type
                if kind in {"requirement_analysis", "code_risk_analysis"}
                and requirement is not None
                else (
                    "daily_metrics"
                    if kind == "test_report"
                    else body.get("sourceType") or body.get("source_type") or "manual"
                )
            ),
            source_content=str(
                ""
                if kind == "ui"
                else requirement.document_content
                if kind in {"requirement_analysis", "code_risk_analysis"}
                and requirement is not None
                else body.get("sourceContent") or body.get("source_content") or ""
            ),
            instruction=str(body.get("instruction") or ""),
        )
        self.repository.add(task)
        await self.repository.commit()
        await self.repository.refresh(task)
        return dump_task(task)

    async def list(self, kind: str, project_id: str, user_id: str) -> dict[str, Any]:
        await self.ensure_project_access(user_id, project_id, action="read")
        rows = await self.repository.list_tasks(project_id, task_type_for(kind))
        payloads = []
        for row in rows:
            archive = (
                await self.source_archive_repository.get_source_archive(row.task_id)
                if kind == "ui"
                else None
            )
            payloads.append(dump_task(row, archive))
        return list_payload(payloads)

    async def get(self, kind: str, task_id: str, user_id: str) -> dict:
        task = await self.owned_task(user_id, task_id, kind, action="read")
        archive = (
            await self.source_archive_repository.get_source_archive(task.task_id)
            if kind == "ui"
            else None
        )
        return dump_task(task, archive)

    async def upload_source_archive(
        self, task_id: str, filename: str, content: bytes, user_id: str
    ) -> dict[str, Any]:
        workflow = SourceArchiveManager(
            source_archive_repository=self.source_archive_repository,
            source_archive_storage_root=self.source_archive_storage_root,
            owned_task=self.owned_task,
            id_factory=new_id,
        )
        return await workflow.upload_source_archive(task_id, filename, content, user_id)

    async def update(self, kind: str, task_id: str, body: dict[str, Any], user_id: str) -> dict:
        task = await self.owned_task(user_id, task_id, kind, action="write")
        if kind == "ui":
            requirement_key = "requirementId" if "requirementId" in body else "requirement_id"
            if requirement_key in body:
                requirement_id = str(body.get(requirement_key) or "")
                if not requirement_id:
                    raise ErrBadRequest
                requirement = await self.repository.get_requirement(requirement_id)
                if requirement is None:
                    raise ErrNotFound
                sprint = await self.repository.get_sprint(requirement.sprint_id)
                if sprint is None or sprint.project_id != task.project_id:
                    raise ErrNotFound
                await self.ensure_requirement_access(user_id, requirement_id, action="write")
                task.requirement_id = requirement_id
                task.sprint_id = requirement.sprint_id
            field_map = {"name": "name", "instruction": "instruction"}
            task.source_type = "source_archive"
            task.source_content = ""
        else:
            field_map = {
                "name": "name",
                "sourceType": "source_type",
                "source_type": "source_type",
                "sourceContent": "source_content",
                "source_content": "source_content",
                "instruction": "instruction",
            }
        for key, attr in field_map.items():
            if key in body:
                setattr(task, attr, body[key])
        await self.repository.commit()
        await self.repository.refresh(task)
        archive = (
            await self.source_archive_repository.get_source_archive(task.task_id)
            if kind == "ui"
            else None
        )
        return dump_task(task, archive)

    async def delete(self, kind: str, task_id: str, user_id: str) -> dict:
        task = await self.owned_task(user_id, task_id, kind, action="write")
        await self.repository.hard_delete(task)
        await self.repository.commit()
        return {}

    async def delete_run(self, kind: str, run_id: str, user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, kind, action="write")
        if run.status in RUN_ACTIVE_STATUSES:
            raise ErrAiGenerateTaskRunRunning
        await self.repository.hard_delete(run)
        await self.repository.commit()
        return {}

    async def test_report_task_for_run(
        self, project_id: str, body: dict[str, Any], user_id: str
    ) -> AiGenerateTask:
        workflow = TestReportWorkflow(
            repository=self.repository,
            sprint_daily_metrics_service=self.sprint_daily_metrics_service,
            ensure_project_access=self.ensure_project_access,
            owned_run=self.owned_run,
            id_factory=new_id,
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
        )
        return await workflow.list_test_report_runs(project_id, sprint_id, user_id)

    async def export_test_report_pdf(self, run_id: str, user_id: str) -> tuple[bytes, str]:
        workflow = TestReportWorkflow(
            repository=self.repository,
            sprint_daily_metrics_service=self.sprint_daily_metrics_service,
            ensure_project_access=self.ensure_project_access,
            owned_run=self.owned_run,
            id_factory=new_id,
        )
        return await workflow.export_test_report_pdf(run_id, user_id)

    async def run(self, kind: str, task_id: str, body: dict[str, Any] | None, user_id: str) -> dict:
        task = await self.owned_task(user_id, task_id, kind, action="execute")
        body = body or {}
        if kind == "ui" and (
            await self.source_archive_repository.get_source_archive(task.task_id) is None
        ):
            raise ErrBadRequest
        llm_connection_id = str(body.get("connectionId") or body.get("llmConnectionId") or "")
        if not llm_connection_id:
            raise ErrBadRequest
        await require_personal_connection(
            self.repository.session, user_id, "llm", llm_connection_id, task.project_id
        )
        run_id = new_id()
        worker_task_id = new_id()
        run_instruction = body.get("instruction")
        if kind == "test_report":
            snapshot_date = str(body.get("snapshotDate") or body.get("snapshot_date") or "")
            if not snapshot_date:
                raise ErrBadRequest
            if self.sprint_daily_metrics_service is None:
                raise ErrBadRequest
            daily_metrics = await self.sprint_daily_metrics_service.get(
                task.sprint_id, snapshot_date, user_id
            )
            snapshot = build_test_report_run_snapshot(
                task,
                run_id,
                snapshot_date,
                daily_metrics,
                llm_connection_id,
                None if run_instruction is None else str(run_instruction),
            )
        elif kind == "code_risk_analysis":
            if self.code_risk_analysis_service is None:
                raise ErrBadRequest
            snapshot = await self.code_risk_analysis_service.build_snapshot(
                task,
                run_id,
                worker_task_id,
                None if run_instruction is None else str(run_instruction),
                user_id=user_id,
                connection_ids=body.get("gitlabConnectionIds") or {},
            )
        else:
            snapshot = await build_generate_run_snapshot(
                self.repository,
                kind,
                task,
                run_id,
                None if run_instruction is None else str(run_instruction),
                worker_task_id=worker_task_id,
            )
        checkpoint_enabled = (
            True if kind == "requirement_analysis" else bool(body.get("checkpointEnabled", False))
        )
        current_stage = ""
        if checkpoint_enabled:
            if kind == "function":
                current_stage = "requirement_analysis"
            elif kind == "requirement_analysis":
                current_stage = REQUIREMENT_ANALYSIS_INITIAL_STAGE
        stage_status = StageStatus.PENDING.value if current_stage else ""
        run = AiGenerateTaskRun(
            run_id=run_id,
            task_id=task.task_id,
            requirement_id=task.requirement_id,
            sprint_id=task.sprint_id,
            project_id=task.project_id,
            trigger_user_id=user_id,
            trigger_type=str(body.get("triggerType") or "manual"),
            status=RunStatus.PENDING.value,
            checkpoint_enabled=checkpoint_enabled,
            current_stage=current_stage,
            stage_status=stage_status,
            snapshot_json=snapshot,
            config_json=normalize_config_json(body.get("configJson")),
            result_summary_json={},
        )
        worker_task = WorkerTask(
            domain="ai",
            task_id=worker_task_id,
            task_type=task.task_type,
            run_id=run.run_id,
            generate_task_id=task.task_id,
            llm_connection_id=llm_connection_id,
            status=RunStatus.PENDING.value,
        )
        self.repository.add_all([run, worker_task])
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def update_result(
        self, kind: str, run_id: str, result_yaml: str, user_id: str
    ) -> dict[str, Any]:
        if kind not in {"api", "function", "ui"}:
            raise ErrBadRequest
        run = await self.owned_run(user_id, run_id, kind, action="write")
        if run.status != RunStatus.SUCCESS.value or run.review_status != ReviewStatus.PENDING.value:
            raise ErrBadRequest
        if kind == "api":
            payload = parse_import_payload(result_yaml)
            await validate_api_collection_import_payload(
                self.repository, "", payload, check_existing=False
            )
        elif kind == "function":
            cases = generated_function_cases(SimpleNamespace(result_yaml=result_yaml))
            if not cases:
                raise ErrBadRequest
            validate_function_candidate_cases(cases)
        else:
            validate_ui_candidate_cases(result_yaml)
        run.result_yaml = result_yaml
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

    async def list_runs(self, kind: str, task_id: str, user_id: str) -> dict[str, Any]:
        await self.owned_task(user_id, task_id, kind, action="read")
        rows = await self.repository.list_runs(task_id)
        if kind == "code_risk_analysis":
            # 代码风险分析 run 详情追加解析后的 report 结构(工单 07,RC-5)。
            # 函数级导入避免与 services.ai_generate_task 的模块循环依赖。
            from testing_agent.services.code_risk_analysis import dump_code_risk_analysis_run

            dump = dump_code_risk_analysis_run
        else:
            dump = dump_run
        return list_payload([dump(row) for row in rows])

    async def import_requirement_analysis_run(self, run_id: str, user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, "requirement_analysis", action="execute")
        if run.status != RunStatus.SUCCESS.value:
            raise ErrBadRequest
        requirement = await self.repository.get_requirement(run.requirement_id)
        if requirement is None:
            raise ErrNotFound
        await self.ensure_requirement_access(user_id, requirement.requirement_id, action="execute")
        requirement.document_content = requirement_analysis_import_content(run)
        await self.repository.commit()
        await self.repository.refresh(requirement)
        return dump_requirement(requirement)

    async def review(self, kind: str, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, kind, action="review")
        if not is_ai_run_reviewable(run.status):
            raise ErrBadRequest
        if run.review_status != ReviewStatus.PENDING.value:
            raise ErrAiGenerateTaskRunReviewed
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
                    raise ErrBadRequest
                if kind == "api":
                    await validate_api_collection_import_payload(
                        self.repository, "", generated_payload(run)
                    )
                elif kind == "function":
                    cases = generated_function_cases(run)
                    if not cases:
                        raise ErrBadRequest
                    validate_function_candidate_cases(cases)
                else:
                    validate_ui_candidate_cases(run.result_yaml)
                run.review_status = ReviewStatus.APPROVED.value
            elif action == "reject":
                run.review_status = ReviewStatus.REJECTED.value
            else:
                raise ErrBadRequest
            run.review_comment = str(body.get("reviewComment") or body.get("comment") or "")
            run.reviewer_user_id = user_id
            run.reviewed_at = datetime.now(UTC)
            await self.repository.commit()
            await self.repository.refresh(run)
            return dump_run(run)
        raise ErrBadRequest

    async def save_stage_output(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository, owned_run=self.owned_run, id_factory=new_id
        )
        return await workflow.save_stage_output(run_id, body, user_id)

    async def save_requirement_analysis_stage_output(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository, owned_run=self.owned_run, id_factory=new_id
        )
        return await workflow.save_requirement_analysis_stage_output(run_id, body, user_id)

    async def review_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository, owned_run=self.owned_run, id_factory=new_id
        )
        return await workflow.review_requirement_analysis_stage(run_id, body, user_id)

    async def revise_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository, owned_run=self.owned_run, id_factory=new_id
        )
        return await workflow.revise_requirement_analysis_stage(run_id, body, user_id)

    async def revise_function_case_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository, owned_run=self.owned_run, id_factory=new_id
        )
        return await workflow.revise_function_case_stage(run_id, body, user_id)

    async def review_stage(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository, owned_run=self.owned_run, id_factory=new_id
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
            repository=self.repository, owned_run=self.owned_run, id_factory=new_id
        )
        return await workflow.retry_stage(run_id, body, user_id, kind=kind)

    async def generate_relation_analysis(
        self, run_id: str, body: dict[str, Any] | None, user_id: str
    ) -> dict:
        workflow = GenerationStageWorkflow(
            repository=self.repository, owned_run=self.owned_run, id_factory=new_id
        )
        return await workflow.generate_relation_analysis(run_id, body, user_id)
