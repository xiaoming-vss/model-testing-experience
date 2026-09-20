from __future__ import annotations

import builtins
import hashlib
import io
import json
import posixpath
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import yaml
from fastapi.encoders import jsonable_encoder

from testing_agent.domain.function_case_content import set_legacy_content
from testing_agent.domain.function_case_identity import pinned_case_id
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.project_access import ProjectAction, require_project_access

if TYPE_CHECKING:
    from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService

from testing_agent.core.enums import ImportStatus, ReviewStatus, RunStatus, StageStatus
from testing_agent.core.errors import (
    AppError,
    ErrAiGenerateTaskRunReviewed,
    ErrBadRequest,
    ErrForbidden,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.schemas.requirement import normalize_document_type
from testing_agent.services.api_collection import (
    import_items,
    int_value,
    normalize_import_body_type,
    normalize_import_method,
    normalize_json_value,
    parse_import_payload,
    require_string_map,
    validate_api_collection_import_payload,
)
from testing_agent.services.common import list_payload
from testing_agent.services.requirement import dump_requirement
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService
from testing_agent.services.test_report_pdf import markdown_to_pdf_bytes
from testing_agent.services.ui_test_case import ui_import_cases


def task_type_for(kind: str) -> str:
    if kind == "ui":
        return "ui_case_generate"
    if kind == "function":
        return "functional_case_generate"
    if kind == "requirement_analysis":
        return "requirement_analysis"
    if kind == "test_report":
        return "test_report_generate"
    if kind == "test_order_graph":
        return "test_order_graph"
    if kind == "code_risk_analysis":
        return "code_risk_analysis"
    return "api_case_generate"


FUNCTION_CASE_REVIEWABLE_STAGES = {"requirement_analysis", "case_names"}
FUNCTION_CASE_REVIEW_READY_STATUSES = {"waiting_review", "saved"}
FUNCTION_CASE_NEXT_STAGE = {
    "requirement_analysis": "case_names",
    "case_names": "detailed_cases",
}
FUNCTION_CASE_RELATION_STAGE = "relation_analysis"
FUNCTION_CASE_RELATION_DISPATCH_STATUSES = {"pending", "claimed", "running"}
REQUIREMENT_ANALYSIS_INITIAL_STAGE = "extracting_text"
REQUIREMENT_ANALYSIS_FINAL_STAGE = "feature_understanding"
REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES = {REQUIREMENT_ANALYSIS_FINAL_STAGE, "completed"}
REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES = {"extracting_text", "writing_requirement"}
REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES = {"waiting_review", "saved"}
REQUIREMENT_ANALYSIS_NEXT_STAGE = {
    "extracting_text": "writing_requirement",
    "writing_requirement": "feature_understanding",
}
REVISION_INSTRUCTION_FIELD = "revisionInstruction"
DEFAULT_FUNCTION_CASE_MODULE = "未分组"

MAX_SOURCE_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_SOURCE_ARCHIVE_FILES = 50_000


def dump_source_archive(archive: AiGenerateTaskSourceArchive | Any | None) -> dict[str, Any] | None:
    if archive is None:
        return None
    return {
        "archiveId": archive.archive_id,
        "filename": archive.filename,
        "sizeBytes": archive.size_bytes,
        "sha256": archive.sha256,
        "uploadedAt": archive.uploaded_at,
    }


def _canonical_archive_path(name: str) -> str:
    normalized = name.replace("\\", "/")
    windows_path = PureWindowsPath(name)
    if (
        not normalized
        or "\x00" in normalized
        or PurePosixPath(normalized).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
    ):
        raise ErrBadRequest
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        raise ErrBadRequest
    canonical = posixpath.normpath(normalized).rstrip("/")
    if canonical in {"", "."}:
        raise ErrBadRequest
    return canonical.casefold()


def validate_source_archive(filename: str, content: bytes) -> None:
    if Path(filename).suffix.casefold() != ".zip":
        raise ErrBadRequest
    if len(content) > MAX_SOURCE_ARCHIVE_BYTES:
        raise ErrBadRequest
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            paths: set[str] = set()
            file_count = 0
            total_size = 0
            for item in archive.infolist():
                canonical_path = _canonical_archive_path(item.filename)
                if canonical_path in paths:
                    raise ErrBadRequest
                paths.add(canonical_path)
                unix_mode = item.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise ErrBadRequest
                if item.is_dir():
                    continue
                file_count += 1
                total_size += item.file_size
                if (
                    file_count > MAX_SOURCE_ARCHIVE_FILES
                    or total_size > MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES
                ):
                    raise ErrBadRequest
                with archive.open(item) as member:
                    while member.read(1024 * 1024):
                        pass
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError) as exc:
        raise ErrBadRequest from exc


def next_function_case_stage(stage: str) -> str | None:
    return FUNCTION_CASE_NEXT_STAGE.get(stage)


def next_requirement_analysis_stage(stage: str) -> str | None:
    return REQUIREMENT_ANALYSIS_NEXT_STAGE.get(stage)


def dump_task(
    task: AiGenerateTask, source_archive: AiGenerateTaskSourceArchive | Any | None = None
) -> dict[str, Any]:
    return {
        "taskId": task.task_id,
        "taskType": task.task_type,
        "name": task.name,
        "projectId": task.project_id,
        "sprintId": task.sprint_id,
        "requirementId": task.requirement_id,
        "creatorUserId": task.creator_user_id,
        "sourceType": task.source_type,
        "sourceContent": task.source_content,
        "sourceArchive": dump_source_archive(source_archive),
        "instruction": task.instruction,
        "createdAt": task.created_at,
        "updatedAt": task.updated_at,
    }


def dump_run(run: AiGenerateTaskRun) -> dict[str, Any]:
    return {
        "runId": run.run_id,
        "taskId": run.task_id,
        "requirementId": run.requirement_id,
        "sprintId": run.sprint_id,
        "projectId": run.project_id,
        "triggerUserId": run.trigger_user_id,
        "triggerType": run.trigger_type,
        "status": run.status,
        "checkpointEnabled": run.checkpoint_enabled,
        "currentStage": run.current_stage,
        "stageStatus": run.stage_status,
        "snapshotJson": run.snapshot_json or {},
        "errorMessage": run.error_message,
        "remediation": str(getattr(run, "remediation", "") or ""),
        "configJson": run.config_json or {},
        "resultYaml": run.result_yaml,
        "resultSummaryJson": run.result_summary_json or {},
        "reviewStatus": run.review_status,
        "importStatus": getattr(run, "import_status", "pending"),
        "importedTargets": getattr(run, "imported_targets", None) or [],
        "importedAt": getattr(run, "imported_at", None),
        "importMigrationComplete": getattr(run, "import_migration_complete", True),
        "reviewerUserId": run.reviewer_user_id,
        "reviewedAt": run.reviewed_at,
        "reviewComment": run.review_comment,
        "durationMs": run.duration_ms,
    }


def requirement_source_content(requirement: Any) -> str:
    document_content = str(getattr(requirement, "document_content", "") or "")
    if document_content.strip():
        return document_content
    storage_path = str(getattr(requirement, "document_storage_path", "") or "")
    if not storage_path:
        return document_content

    path = Path(storage_path)
    document_type = normalize_document_type(
        str(getattr(requirement, "document_type", "") or "text")
    )
    if document_type == "text" and path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return document_content


def requirement_document_download_url(requirement: Any, requirement_id: str) -> str:
    document_download_url = str(getattr(requirement, "document_download_url", "") or "")
    if document_download_url:
        return document_download_url

    resolved_requirement_id = str(
        getattr(requirement, "requirement_id", "") or requirement_id or ""
    )
    if not resolved_requirement_id:
        return ""
    return f"/v1/requirements/{resolved_requirement_id}/download"


def worker_requirement_document_download_url(worker_task_id: str) -> str:
    return f"/internal/ai-worker/tasks/{worker_task_id}/requirement-document"


def worker_source_archive_download_url(worker_task_id: str) -> str:
    return f"/internal/ai-worker/tasks/{worker_task_id}/source-archive"


def build_test_report_run_snapshot(
    task: AiGenerateTask,
    run_id: str,
    snapshot_date: str,
    daily_metrics: dict[str, Any],
    llm_connection_id: str,
    instruction: str | None = None,
) -> dict[str, Any]:
    return {
        "taskId": task.task_id,
        "runId": run_id,
        "taskType": task.task_type,
        "name": task.name,
        "projectId": task.project_id,
        "sprintId": task.sprint_id,
        "requirementId": task.requirement_id,
        "snapshotDate": snapshot_date,
        "llmConnectionId": llm_connection_id,
        "dailyMetrics": jsonable_encoder(daily_metrics),
        "instruction": task.instruction if instruction is None else instruction,
    }


async def build_generate_run_snapshot(
    repository: AiGenerateTaskRepository,
    kind: str,
    task: AiGenerateTask,
    run_id: str,
    instruction: str | None = None,
    worker_task_id: str | None = None,
) -> dict[str, Any]:
    source_content = task.source_content
    document_type = ""
    document_download_url = ""
    uses_requirement_document = False
    if kind in {"function", "requirement_analysis"}:
        requirement = await repository.get_requirement(task.requirement_id)
        if (
            kind == "function"
            and not str(getattr(requirement, "document_content", "") or "").strip()
        ):
            raise AppError(400, "请先完成需求分析并导入增强文本，再生成功能用例", 400)
        if requirement is not None:
            uses_requirement_document = True
            document_type = normalize_document_type(str(requirement.document_type or "text"))
            document_download_url = (
                worker_requirement_document_download_url(worker_task_id)
                if worker_task_id
                else requirement_document_download_url(requirement, str(task.requirement_id or ""))
            )
            source_content = requirement_source_content(requirement)
            if not source_content and document_type == "docx":
                source_content = document_download_url
    elif kind == "ui":
        requirement = await repository.get_requirement(task.requirement_id)
        if requirement is not None:
            # Requirement analysis imports its enhanced text into document_content.
            # UI generation consumes only that text; it must not fall back to the
            # original requirement document or expose a document download URL.
            source_content = str(getattr(requirement, "document_content", "") or "")
    snapshot = {
        "taskId": task.task_id,
        "runId": run_id,
        "taskType": task.task_type,
        "name": task.name,
        "projectId": task.project_id,
        "sprintId": task.sprint_id,
        "requirementId": task.requirement_id,
        "sourceContent": source_content,
        "instruction": task.instruction if instruction is None else instruction,
    }
    if uses_requirement_document:
        snapshot["documentType"] = document_type
        snapshot["documentDownloadUrl"] = document_download_url
    else:
        snapshot["sourceType"] = task.source_type
    if kind == "ui" and worker_task_id:
        snapshot["sourceArchiveDownloadUrl"] = worker_source_archive_download_url(worker_task_id)
    return snapshot


def generated_payload(run: AiGenerateTaskRun | Any) -> dict[str, Any]:
    raw = run.result_yaml or ""
    if not raw.strip():
        raise ErrBadRequest
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ErrBadRequest from exc
    return parse_import_payload(data)


def generated_api_cases(run: AiGenerateTaskRun | Any) -> builtins.list[dict[str, Any]]:
    return [
        item
        for item in import_items(generated_payload(run), "cases", "apiCases")
        if isinstance(item, dict)
    ]


def generated_function_suites(run: AiGenerateTaskRun | Any) -> builtins.list[dict[str, Any]]:
    payload = generated_payload(run)
    raw_suites = payload.get("suites")
    if isinstance(raw_suites, list):
        return [suite for suite in raw_suites if isinstance(suite, dict)]
    cases = [
        item
        for item in import_items(payload, "cases", "functionCases", "testcases")
        if isinstance(item, dict)
    ]
    return [{"name": "AI Generated", "cases": cases}] if cases else []


def generated_function_cases(run: AiGenerateTaskRun | Any) -> builtins.list[dict[str, Any]]:
    payload = generated_payload(run)
    cases = [
        item
        for item in import_items(payload, "cases", "functionCases", "testcases")
        if isinstance(item, dict)
    ]
    if cases:
        return cases

    result: builtins.list[dict[str, Any]] = []
    raw_suites = payload.get("suites")
    if isinstance(raw_suites, list):
        for suite in raw_suites:
            if not isinstance(suite, dict):
                continue
            suite_name = str(suite.get("name") or "")
            suite_cases = suite.get("cases")
            if not isinstance(suite_cases, list):
                continue
            for item in suite_cases:
                if not isinstance(item, dict):
                    continue
                case = dict(item)
                if not case.get("case_module") and not case.get("module"):
                    case["module"] = suite_name
                result.append(case)
    return result


def first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    return None


def import_lines(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(line).strip() for line in value)
    return str(value).strip()


def normalize_function_case_module(value: Any) -> str:
    module = str(value or "").strip()
    return module or DEFAULT_FUNCTION_CASE_MODULE


def normalize_generated_function_case(item: dict[str, Any], index: int) -> dict[str, Any]:
    module = normalize_function_case_module(first_present(item, "case_module", "module"))
    title = str(first_present(item, "case_title", "title", "name") or "").strip()
    priority = str(first_present(item, "priority") or "")
    case_type = str(first_present(item, "case_type", "caseType") or "")
    case_id = str(first_present(item, "case_id", "caseId") or "").strip()
    if (
        not title
        or len(title) > 255
        or len(module) > 120
        or len(priority) > 20
        or len(case_type) > 50
        or len(case_id) > 64
    ):
        raise ErrBadRequest
    return {
        "case_id": case_id,
        "module": module,
        "title": title,
        "preconditions": import_lines(first_present(item, "precondition", "preconditions")),
        "steps": import_lines(first_present(item, "test_steps", "steps")),
        "expected_results": import_lines(
            first_present(item, "expected_results", "expectedResults")
        ),
        "priority": priority,
        "case_type": case_type,
        "order_no": int(first_present(item, "orderNo", "order_no") or index),
    }


def validate_function_candidate_cases(
    cases: builtins.list[dict[str, Any]],
) -> builtins.list[dict[str, Any]]:
    normalized_cases: builtins.list[dict[str, Any]] = []
    names: set[tuple[str, str]] = set()
    for index, item in enumerate(cases):
        case = normalize_generated_function_case(item, index)
        key = (case["module"].casefold(), case["title"].casefold())
        if key in names:
            raise ErrBadRequest
        names.add(key)
        normalized_cases.append(case)
    return normalized_cases


def is_ai_run_reviewable(status: str) -> bool:
    return status in {"success", "failed", "error", "canceled"}


def bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def normalize_config_json(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ErrBadRequest from exc
        if isinstance(parsed, dict):
            return parsed
    raise ErrBadRequest


def normalize_function_stage_config(stage: str, value: Any) -> dict[str, Any]:
    config = dict(normalize_config_json(value))
    if stage == "requirement_analysis" and "requirementAnalysis" not in config:
        return {"requirementAnalysis": config}
    if stage == "case_names" and "categories" in config:
        case_names = config.get("caseNames")
        if not isinstance(case_names, dict):
            case_names = {}
        config["caseNames"] = {**case_names, "categories": config.pop("categories")}
    return config


def requirement_analysis_import_content(run: AiGenerateTaskRun | Any) -> str:
    result_yaml = str(run.result_yaml or "").strip()
    if result_yaml:
        return result_yaml
    summary = run.result_summary_json
    if isinstance(summary, str):
        summary_text = summary.strip()
        if summary_text:
            return summary_text
    elif summary:
        return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    raise ErrBadRequest


def validate_ui_candidate_cases(result_yaml: str) -> builtins.list[dict[str, Any]]:
    payload = generated_payload(SimpleNamespace(result_yaml=result_yaml))
    try:
        cases = ui_import_cases(payload)
    except AppError as exc:
        raise ErrBadRequest from exc
    if not cases:
        raise ErrBadRequest
    for case in cases:
        if (
            not isinstance(case, dict)
            or not isinstance(case.get("name"), str)
            or not case["name"].strip()
            or not isinstance(case.get("enabled"), bool)
            or not isinstance(case.get("orderNo"), int)
            or isinstance(case.get("orderNo"), bool)
            or not isinstance(case.get("stepsJson"), list)
        ):
            raise ErrBadRequest
        for step in case["stepsJson"]:
            if (
                not isinstance(step, dict)
                or not isinstance(step.get("keyword"), str)
                or not step["keyword"].strip()
            ):
                raise ErrBadRequest
    return cases


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

    async def stage_connection(self, run, body, user_id, previous_id):
        connection_id = str(
            body.get("connectionId") or body.get("llmConnectionId") or previous_id or ""
        )
        connection = await require_personal_connection(
            self.repository.session, user_id, "llm", connection_id, run.project_id
        )
        return connection.connection_id

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
        task = await self.owned_task(user_id, task_id, "ui", action="write")
        safe_filename = Path(filename).name
        validate_source_archive(safe_filename, content)

        archive_id = new_id()
        uploaded_at = datetime.now(UTC)
        task_storage_root = self.source_archive_storage_root / task.task_id
        target_path = task_storage_root / f"{archive_id}.zip"
        temporary_path = task_storage_root / f".{archive_id}.tmp"
        task_storage_root.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(content)
        temporary_path.replace(target_path)

        source_repository = self.source_archive_repository
        archive = await source_repository.get_source_archive_for_update(task.task_id)
        old_path = Path(archive.storage_path) if archive is not None else None
        if archive is None:
            archive = AiGenerateTaskSourceArchive(
                archive_id=archive_id,
                task_id=task.task_id,
                filename=safe_filename,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                storage_path=str(target_path),
                uploaded_at=uploaded_at,
            )
            source_repository.add(archive)
        else:
            archive.archive_id = archive_id
            archive.filename = safe_filename
            archive.size_bytes = len(content)
            archive.sha256 = hashlib.sha256(content).hexdigest()
            archive.storage_path = str(target_path)
            archive.uploaded_at = uploaded_at

        try:
            await source_repository.commit()
        except Exception:
            target_path.unlink(missing_ok=True)
            if hasattr(source_repository, "rollback"):
                await source_repository.rollback()
            raise

        if old_path is not None and old_path != target_path:
            try:
                if old_path.resolve().is_relative_to(self.source_archive_storage_root.resolve()):
                    old_path.unlink(missing_ok=True)
            except OSError:
                pass
        return dump_task(task, archive)

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

    async def test_report_task_for_run(
        self, project_id: str, body: dict[str, Any], user_id: str
    ) -> AiGenerateTask:
        await self.ensure_project_access(user_id, project_id, action="execute")
        sprint_id = str(body.get("sprintId") or body.get("sprint_id") or "")
        if not sprint_id:
            raise ErrBadRequest
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrNotFound
        existing = await self.repository.get_active_task_by_project_sprint_type(
            project_id, sprint_id, task_type_for("test_report")
        )
        if existing is not None:
            return existing
        sprint_name = str(getattr(sprint, "name", "") or "").strip()
        return AiGenerateTask(
            task_id=new_id(),
            task_type=task_type_for("test_report"),
            name=f"{sprint_name} 测试报告生成" if sprint_name else "测试报告生成",
            project_id=project_id,
            sprint_id=sprint_id,
            requirement_id="",
            creator_user_id=user_id,
            source_type="daily_metrics",
            source_content="",
            instruction="",
        )

    async def run_test_report(
        self, project_id: str, body: dict[str, Any] | None, user_id: str
    ) -> dict:
        body = body or {}
        llm_connection_id = str(body.get("connectionId") or body.get("llmConnectionId") or "")
        snapshot_date = str(body.get("snapshotDate") or body.get("snapshot_date") or "")
        if not llm_connection_id or not snapshot_date:
            raise ErrBadRequest
        task = await self.test_report_task_for_run(project_id, body, user_id)
        await require_personal_connection(
            self.repository.session, user_id, "llm", llm_connection_id, task.project_id
        )
        run_id = new_id()
        worker_task_id = new_id()
        if self.sprint_daily_metrics_service is None:
            raise ErrBadRequest
        daily_metrics = await self.sprint_daily_metrics_service.get(
            task.sprint_id, snapshot_date, user_id
        )
        run_instruction = body.get("instruction")
        snapshot = build_test_report_run_snapshot(
            task,
            run_id,
            snapshot_date,
            daily_metrics,
            llm_connection_id,
            None if run_instruction is None else str(run_instruction),
        )
        run = AiGenerateTaskRun(
            run_id=run_id,
            task_id=task.task_id,
            requirement_id="",
            sprint_id=task.sprint_id,
            project_id=task.project_id,
            trigger_user_id=user_id,
            trigger_type=str(body.get("triggerType") or "manual"),
            status=RunStatus.PENDING.value,
            checkpoint_enabled=False,
            current_stage="",
            stage_status="",
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
        rows: builtins.list[object] = [run, worker_task]
        if getattr(task, "id", None) is None:
            rows.insert(0, task)
        self.repository.add_all(rows)
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def list_test_report_runs(
        self, project_id: str, sprint_id: str, user_id: str
    ) -> dict[str, Any]:
        await self.ensure_project_access(user_id, project_id, action="read")
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrNotFound
        rows = await self.repository.list_runs_by_project_sprint_task_type(
            project_id, sprint_id, task_type_for("test_report")
        )
        return list_payload([dump_run(row) for row in rows])

    async def export_test_report_pdf(self, run_id: str, user_id: str) -> tuple[bytes, str]:
        run = await self.owned_run(user_id, run_id, "test_report", action="read")
        markdown = str(run.result_yaml or "").strip()
        if not markdown:
            raise ErrBadRequest
        snapshot = run.snapshot_json if isinstance(run.snapshot_json, dict) else {}
        title = str(snapshot.get("name") or "测试报告")
        filename = f"test-report-{run.run_id}.pdf"
        return markdown_to_pdf_bytes(markdown, title=title), filename

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

    @staticmethod
    def _normalized_api_case_name(name: Any) -> str:
        return str(name or "").strip().casefold()

    @staticmethod
    def _generated_api_case(item: dict[str, Any], index: int) -> dict[str, Any]:
        body_type = normalize_import_body_type(item.get("bodyType"))
        body_json = normalize_json_value(item.get("bodyJson"))
        body_text = str(item.get("bodyText") or "")
        if body_type == "raw":
            body_json = None
        elif body_type == "none":
            body_json = None
            body_text = ""
        extract_rules = item.get("extractRules") or []
        assert_rules = item.get("assertRules") or []
        return {
            "name": str(item.get("name") or f"API Case {index + 1}").strip(),
            "description": str(item.get("description") or ""),
            "enabled": bool_value(item.get("enabled"), True),
            "orderNo": int_value(item.get("orderNo"), 0),
            "method": normalize_import_method(item.get("method")),
            "urlTemplate": str(item.get("urlTemplate") or ""),
            "headers": require_string_map(item.get("headers"), f"cases[{index}].headers"),
            "query": require_string_map(item.get("query"), f"cases[{index}].query"),
            "bodyType": body_type,
            "bodyJson": body_json,
            "bodyText": body_text,
            "timeoutMs": int_value(item.get("timeoutMs"), 5000),
            "continueOnFailure": bool_value(item.get("continueOnFailure"), False),
            "extractRules": [
                {
                    "name": str(rule.get("name") or f"Extract Rule {rule_index + 1}"),
                    "enabled": bool_value(rule.get("enabled"), True),
                    "orderNo": int_value(rule.get("orderNo"), rule_index),
                    "source": str(rule.get("source") or ""),
                    "sourceExpr": str(rule.get("sourceExpr") or ""),
                    "varKey": str(rule.get("varKey") or "").strip(),
                    "defaultValue": str(rule.get("defaultValue") or ""),
                }
                for rule_index, rule in enumerate(extract_rules)
                if isinstance(rule, dict)
            ],
            "assertRules": [
                {
                    "name": str(rule.get("name") or f"Assert Rule {rule_index + 1}"),
                    "enabled": bool_value(rule.get("enabled"), True),
                    "orderNo": int_value(rule.get("orderNo"), rule_index),
                    "assertSource": str(rule.get("assertSource") or ""),
                    "targetExpr": str(rule.get("targetExpr") or ""),
                    "comparator": str(rule.get("comparator") or ""),
                    "expectedValue": str(rule.get("expectedValue") or ""),
                }
                for rule_index, rule in enumerate(assert_rules)
                if isinstance(rule, dict)
            ],
        }

    async def _stored_api_case(self, case: ApiCase) -> dict[str, Any]:
        extract_rules = await self.repository.list_api_extract_rules(case.case_id)
        assert_rules = await self.repository.list_api_assert_rules(case.case_id)
        return {
            "name": case.name,
            "description": case.description,
            "enabled": case.enabled,
            "orderNo": case.order_no,
            "method": case.method,
            "urlTemplate": case.url_template,
            "headers": case.headers_json or {},
            "query": case.query_json or {},
            "bodyType": case.body_type,
            "bodyJson": case.body_json,
            "bodyText": case.body_text,
            "timeoutMs": case.timeout_ms,
            "continueOnFailure": case.continue_on_failure,
            "extractRules": [
                {
                    "name": rule.name,
                    "enabled": rule.enabled,
                    "orderNo": rule.order_no,
                    "source": rule.source,
                    "sourceExpr": rule.source_expr,
                    "varKey": rule.var_key,
                    "defaultValue": rule.default_value,
                }
                for rule in extract_rules
            ],
            "assertRules": [
                {
                    "name": rule.name,
                    "enabled": rule.enabled,
                    "orderNo": rule.order_no,
                    "assertSource": rule.assert_source,
                    "targetExpr": rule.target_expr,
                    "comparator": rule.comparator,
                    "expectedValue": rule.expected_value,
                }
                for rule in assert_rules
            ],
        }

    @staticmethod
    def _apply_api_case(case: ApiCase, item: dict[str, Any]) -> None:
        case.name = item["name"]
        case.description = item["description"]
        case.enabled = item["enabled"]
        case.order_no = item["orderNo"]
        case.method = item["method"]
        case.url_template = item["urlTemplate"]
        case.headers_json = item["headers"]
        case.query_json = item["query"]
        case.body_type = item["bodyType"]
        case.body_json = item["bodyJson"]
        case.body_text = item["bodyText"]
        case.timeout_ms = item["timeoutMs"]
        case.continue_on_failure = item["continueOnFailure"]

    def _add_api_rules(self, case_id: str, item: dict[str, Any]) -> None:
        for rule in item["extractRules"]:
            self.repository.add(
                ApiExtractRule(
                    extract_rule_id=new_id(),
                    case_id=case_id,
                    name=rule["name"],
                    enabled=rule["enabled"],
                    order_no=rule["orderNo"],
                    source=rule["source"],
                    source_expr=rule["sourceExpr"],
                    var_key=rule["varKey"],
                    default_value=rule["defaultValue"],
                )
            )
        for rule in item["assertRules"]:
            self.repository.add(
                ApiAssertRule(
                    assert_rule_id=new_id(),
                    case_id=case_id,
                    name=rule["name"],
                    enabled=rule["enabled"],
                    order_no=rule["orderNo"],
                    assert_source=rule["assertSource"],
                    target_expr=rule["targetExpr"],
                    comparator=rule["comparator"],
                    expected_value=rule["expectedValue"],
                )
            )

    async def _replace_api_rules(self, case_id: str, item: dict[str, Any]) -> None:
        existing_extract = {
            rule.var_key: rule for rule in await self.repository.list_api_extract_rules(case_id)
        }
        existing_assert = {
            rule.name: rule for rule in await self.repository.list_api_assert_rules(case_id)
        }
        generated_extract = {rule["varKey"]: rule for rule in item["extractRules"]}
        generated_assert = {rule["name"]: rule for rule in item["assertRules"]}
        for extract_key, extract_rule in list(existing_extract.items()):
            if extract_key not in generated_extract:
                await self.repository.delete(extract_rule)
        for assert_key, assert_rule in list(existing_assert.items()):
            if assert_key not in generated_assert:
                await self.repository.delete(assert_rule)
        await self.repository.flush()
        for key, values in generated_extract.items():
            matched_extract = existing_extract.get(key)
            if matched_extract is None:
                self.repository.add(
                    ApiExtractRule(
                        extract_rule_id=new_id(),
                        case_id=case_id,
                        name=values["name"],
                        enabled=values["enabled"],
                        order_no=values["orderNo"],
                        source=values["source"],
                        source_expr=values["sourceExpr"],
                        var_key=key,
                        default_value=values["defaultValue"],
                    )
                )
            else:
                matched_extract.name = values["name"]
                matched_extract.enabled = values["enabled"]
                matched_extract.order_no = values["orderNo"]
                matched_extract.source = values["source"]
                matched_extract.source_expr = values["sourceExpr"]
                matched_extract.default_value = values["defaultValue"]
        for key, values in generated_assert.items():
            matched_assert = existing_assert.get(key)
            if matched_assert is None:
                self.repository.add(
                    ApiAssertRule(
                        assert_rule_id=new_id(),
                        case_id=case_id,
                        name=key,
                        enabled=values["enabled"],
                        order_no=values["orderNo"],
                        assert_source=values["assertSource"],
                        target_expr=values["targetExpr"],
                        comparator=values["comparator"],
                        expected_value=values["expectedValue"],
                    )
                )
            else:
                matched_assert.enabled = values["enabled"]
                matched_assert.order_no = values["orderNo"]
                matched_assert.assert_source = values["assertSource"]
                matched_assert.target_expr = values["targetExpr"]
                matched_assert.comparator = values["comparator"]
                matched_assert.expected_value = values["expectedValue"]

    async def import_api_run(
        self,
        run_id: str,
        collection_id: str,
        confirm_overwrite: bool,
        user_id: str,
    ) -> dict[str, Any]:
        run = await self.owned_run(user_id, run_id, "api", action="execute")
        if (
            run.status != RunStatus.SUCCESS.value
            or run.review_status != ReviewStatus.APPROVED.value
            or run.import_status == ImportStatus.IMPORTED.value
        ):
            raise ErrBadRequest
        await self.ensure_collection_access(user_id, collection_id, action="execute")
        raw_cases = await validate_api_collection_import_payload(
            self.repository,
            collection_id,
            generated_payload(run),
            check_existing=False,
        )
        generated_cases = [
            self._generated_api_case(item, index) for index, item in enumerate(raw_cases)
        ]
        existing_cases = await self.repository.list_api_cases(collection_id)
        existing_by_name: dict[str, ApiCase] = {}
        for case in existing_cases:
            normalized_name = self._normalized_api_case_name(case.name)
            if normalized_name in existing_by_name:
                raise ErrBadRequest
            existing_by_name[normalized_name] = case
        conflicts: builtins.list[dict[str, Any]] = []
        for item in generated_cases:
            normalized_name = self._normalized_api_case_name(item["name"])
            existing = existing_by_name.get(normalized_name)
            if existing is not None:
                conflicts.append(
                    {
                        "normalizedName": normalized_name,
                        "existingCase": await self._stored_api_case(existing),
                        "generatedCase": item,
                    }
                )
        if conflicts and not confirm_overwrite:
            return {
                "requiresConfirmation": True,
                "conflicts": conflicts,
                "run": dump_run(run),
            }

        old_import_state = (
            run.import_status,
            run.imported_targets,
            run.imported_at,
            run.import_migration_complete,
        )
        try:
            for item in generated_cases:
                normalized_name = self._normalized_api_case_name(item["name"])
                target_case = existing_by_name.get(normalized_name)
                if target_case is None:
                    target_case = ApiCase(case_id=new_id(), collection_id=collection_id)
                    self._apply_api_case(target_case, item)
                    self.repository.add(target_case)
                    self._add_api_rules(target_case.case_id, item)
                else:
                    self._apply_api_case(target_case, item)
                    await self._replace_api_rules(target_case.case_id, item)
            imported_at = datetime.now(UTC)
            run.import_status = ImportStatus.IMPORTED.value
            run.imported_targets = [{"targetType": "api_collection", "targetId": collection_id}]
            run.imported_at = imported_at
            run.import_migration_complete = True
            await self.repository.commit()
            await self.repository.refresh(run)
        except Exception:
            (
                run.import_status,
                run.imported_targets,
                run.imported_at,
                run.import_migration_complete,
            ) = old_import_state
            await self.repository.rollback()
            raise
        return {
            "requiresConfirmation": False,
            "conflicts": [],
            "run": dump_run(run),
        }

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

    def generated_payload(self, run: AiGenerateTaskRun) -> dict[str, Any]:
        return generated_payload(run)

    async def import_generated_api_cases(
        self, user_id: str, run: AiGenerateTaskRun, collection_id: str
    ) -> None:
        await self.ensure_collection_access(user_id, collection_id, action="execute")
        cases = await validate_api_collection_import_payload(
            self.repository, collection_id, generated_payload(run)
        )
        for index, item in enumerate(cases):
            case_id = new_id()
            body_type = normalize_import_body_type(item.get("bodyType"))
            body_json = normalize_json_value(item.get("bodyJson"))
            body_text = str(item.get("bodyText") or "")
            if body_type == "raw":
                body_json = None
            elif body_type == "none":
                body_json = None
                body_text = ""
            self.repository.add(
                ApiCase(
                    case_id=case_id,
                    collection_id=collection_id,
                    name=str(item.get("name") or f"API Case {index + 1}"),
                    description=str(item.get("description") or ""),
                    enabled=bool_value(item.get("enabled"), True),
                    order_no=int_value(item.get("orderNo"), 0),
                    method=normalize_import_method(item.get("method")),
                    url_template=str(item.get("urlTemplate") or ""),
                    headers_json=require_string_map(item.get("headers"), f"cases[{index}].headers"),
                    query_json=require_string_map(item.get("query"), f"cases[{index}].query"),
                    body_type=body_type,
                    body_json=body_json,
                    body_text=body_text,
                    timeout_ms=int_value(item.get("timeoutMs"), 5000),
                    continue_on_failure=bool_value(item.get("continueOnFailure"), False),
                )
            )
            extract_rules = item.get("extractRules")
            if isinstance(extract_rules, list):
                for rule_index, rule in enumerate(extract_rules):
                    if not isinstance(rule, dict):
                        continue
                    self.repository.add(
                        ApiExtractRule(
                            extract_rule_id=new_id(),
                            case_id=case_id,
                            name=str(rule.get("name") or f"Extract Rule {rule_index + 1}"),
                            enabled=bool_value(rule.get("enabled"), True),
                            order_no=int(rule.get("orderNo", rule_index)),
                            source=str(rule.get("source") or ""),
                            source_expr=str(rule.get("sourceExpr") or ""),
                            var_key=str(rule.get("varKey") or ""),
                            default_value=str(rule.get("defaultValue") or ""),
                        )
                    )
            assert_rules = item.get("assertRules")
            if isinstance(assert_rules, list):
                for rule_index, rule in enumerate(assert_rules):
                    if not isinstance(rule, dict):
                        continue
                    self.repository.add(
                        ApiAssertRule(
                            assert_rule_id=new_id(),
                            case_id=case_id,
                            name=str(rule.get("name") or f"Assert Rule {rule_index + 1}"),
                            enabled=bool_value(rule.get("enabled"), True),
                            order_no=int(rule.get("orderNo", rule_index)),
                            assert_source=str(rule.get("assertSource") or ""),
                            target_expr=str(rule.get("targetExpr") or ""),
                            comparator=str(rule.get("comparator") or ""),
                            expected_value=str(rule.get("expectedValue") or ""),
                        )
                    )

    async def import_generated_function_cases(
        self, user_id: str, run: AiGenerateTaskRun
    ) -> builtins.list[str]:
        await self.ensure_requirement_access(user_id, run.requirement_id, action="execute")
        cases = generated_function_cases(run)
        if not cases:
            raise ErrBadRequest

        suites_by_name: dict[str, FunctionTestSuite] = {}
        max_order_by_suite_id: dict[str, int] = {}
        suite_ids: builtins.list[str] = []
        suite_id_set: set[str] = set()

        for case_index, raw_item in enumerate(cases):
            item = normalize_generated_function_case(raw_item, case_index)
            suite_name = item["module"]
            suite = suites_by_name.get(suite_name)
            if suite is None:
                suite = await self.repository.get_function_suite_by_requirement_and_name(
                    run.requirement_id, suite_name
                )
                if suite is None:
                    suite = FunctionTestSuite(
                        suite_id=new_id(),
                        requirement_id=run.requirement_id,
                        name=suite_name,
                        description="",
                    )
                    self.repository.add(suite)
                suites_by_name[suite_name] = suite
            if suite.suite_id not in suite_id_set:
                suite_ids.append(suite.suite_id)
                suite_id_set.add(suite.suite_id)

            existing = await self.repository.get_function_case_by_suite_and_title(
                suite.suite_id, item["title"]
            )
            if existing is not None:
                existing.module = suite.name
                set_legacy_content(
                    existing, item["preconditions"], item["steps"], item["expected_results"]
                )
                existing.priority = item["priority"]
                existing.case_type = item["case_type"]
                continue

            max_order = max_order_by_suite_id.get(suite.suite_id)
            if max_order is None:
                max_order = await self.repository.max_function_case_order_by_suite(suite.suite_id)
            max_order += 1
            max_order_by_suite_id[suite.suite_id] = max_order

            self.repository.add(
                FunctionTestCase(
                    case_id=await pinned_case_id(self.repository, item["case_id"]),
                    suite_id=suite.suite_id,
                    module=suite.name,
                    title=item["title"],
                    preconditions=item["preconditions"],
                    steps=item["steps"],
                    expected_results=item["expected_results"],
                    priority=item["priority"],
                    case_type=item["case_type"],
                    order_no=max_order,
                )
            )
        return suite_ids

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
        run.review_comment = str(body.get("reviewComment") or body.get("comment") or "")
        run.reviewer_user_id = user_id
        run.reviewed_at = datetime.now(UTC)
        if action == "approve":
            if kind == "api":
                collection_id = str(body.get("collectionId") or body.get("collection_id") or "")
                if not collection_id:
                    raise ErrBadRequest
                await self.import_generated_api_cases(user_id, run, collection_id)
                run.imported_targets = [{"targetType": "api_collection", "targetId": collection_id}]
            else:
                suite_ids = await self.import_generated_function_cases(user_id, run)
                run.imported_targets = [
                    {"targetType": "function_suite", "targetId": suite_id} for suite_id in suite_ids
                ]
            run.import_status = ImportStatus.IMPORTED.value
            run.imported_at = run.reviewed_at
            run.import_migration_complete = True
            run.review_status = ReviewStatus.APPROVED.value
        elif action == "reject":
            run.review_status = ReviewStatus.REJECTED.value
            run.import_status = ImportStatus.PENDING.value
            run.imported_targets = []
            run.imported_at = None
            run.import_migration_complete = True
        else:
            raise ErrBadRequest
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def save_stage_output(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, "function", action="review")
        if (
            not run.checkpoint_enabled
            or run.status != "waiting_review"
            or run.stage_status not in FUNCTION_CASE_REVIEW_READY_STATUSES
            or run.current_stage not in FUNCTION_CASE_REVIEWABLE_STAGES
            or run.review_status != ReviewStatus.PENDING.value
            or getattr(run, "import_status", ImportStatus.PENDING.value)
            == ImportStatus.IMPORTED.value
        ):
            raise dynamic_error(ErrBadRequest, "仅允许保存未审核、未导入且等待审核的当前阶段产物")
        if set(body) - {"stage", "currentStage", "configJson"} or "configJson" not in body:
            raise dynamic_error(ErrBadRequest, "阶段保存仅支持当前阶段的 configJson")
        for key in ("stage", "currentStage"):
            if key in body and body[key] != run.current_stage:
                raise dynamic_error(ErrBadRequest, "不能修改其他阶段的产物")
        field = {"requirement_analysis": "requirementAnalysis", "case_names": "caseNames"}[
            run.current_stage
        ]
        raw_config = normalize_config_json(body["configJson"])
        # Stage editors may send a bare artifact, but cannot change another stage.
        if (set(raw_config) & {"enhancedText", "requirementAnalysis", "caseNames"}) - {field}:
            raise dynamic_error(ErrBadRequest, "不能修改其他阶段的产物")
        edits = normalize_function_stage_config(run.current_stage, raw_config)
        if set(edits) != {field} or not isinstance(edits[field], dict) or not edits[field]:
            raise dynamic_error(ErrBadRequest, "阶段产物必须是当前阶段的非空 JSON 对象")
        run.config_json = {**normalize_config_json(run.config_json), field: edits[field]}
        run.stage_status = StageStatus.WAITING_REVIEW.value
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def save_requirement_analysis_stage_output(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        run = await self.owned_run(user_id, run_id, "requirement_analysis", action="review")
        current_stage = str(body.get("currentStage") or body.get("stage") or run.current_stage)
        is_review_stage = (
            run.checkpoint_enabled
            and current_stage == run.current_stage
            and current_stage in REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES
            and run.status == "waiting_review"
            and run.stage_status in REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES
        )
        is_final_stage = (
            run.status == RunStatus.SUCCESS.value
            and current_stage == REQUIREMENT_ANALYSIS_FINAL_STAGE
            and run.current_stage in REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES
        )
        if not (is_review_stage or is_final_stage):
            raise ErrBadRequest
        if is_review_stage:
            run.stage_status = StageStatus.WAITING_REVIEW.value
        if "configJson" in body:
            run.config_json = normalize_config_json(body.get("configJson"))
        if "resultYaml" in body:
            run.result_yaml = str(body.get("resultYaml") or "")
        run.result_summary_json = body.get("resultSummaryJson") or run.result_summary_json
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def review_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        run = await self.owned_run(user_id, run_id, "requirement_analysis", action="review")
        if (
            not run.checkpoint_enabled
            or run.status != "waiting_review"
            or run.stage_status not in REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES
        ):
            raise ErrBadRequest

        current_stage = str(body.get("currentStage") or body.get("stage") or "")
        if (
            current_stage != run.current_stage
            or current_stage not in REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES
        ):
            raise ErrBadRequest

        action = str(
            body.get("action")
            or body.get("reviewStatus")
            or body.get("status")
            or body.get("stageStatus")
            or "approve"
        )
        if action == "approved":
            action = "approve"
        if action == "rejected":
            action = "reject"

        run.review_comment = str(body.get("reviewComment") or body.get("comment") or "")
        run.reviewer_user_id = user_id
        run.reviewed_at = datetime.now(UTC)
        if action == "approve":
            latest_task = await self.repository.get_latest_worker_task_by_run_id(run.run_id)
            next_stage = next_requirement_analysis_stage(run.current_stage)
            if latest_task is None or next_stage is None:
                raise ErrBadRequest
            if "configJson" in body:
                run.config_json = normalize_config_json(body.get("configJson"))
            run.status = RunStatus.PENDING.value
            run.current_stage = next_stage
            run.stage_status = StageStatus.PENDING.value
            run.error_message = ""
            self.repository.add(
                WorkerTask(
                    domain="ai",
                    task_id=new_id(),
                    task_type=task_type_for("requirement_analysis"),
                    run_id=run.run_id,
                    generate_task_id=run.task_id,
                    llm_connection_id=await self.stage_connection(
                        run, body or {}, user_id, latest_task.llm_connection_id
                    ),
                    status=RunStatus.PENDING.value,
                )
            )
        elif action == "reject":
            run.status = RunStatus.CANCELED.value
            run.stage_status = StageStatus.FAILED.value
        else:
            raise ErrBadRequest
        run._stage_review = (
            current_stage,
            "approved" if action == "approve" else "rejected",
            str(body.get("reviewComment") or body.get("comment") or ""),
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def revise_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        run = await self.owned_run(user_id, run_id, "requirement_analysis", action="execute")

        current_stage = str(body.get("currentStage") or body.get("stage") or "")
        is_review_stage = (
            run.checkpoint_enabled
            and run.status == "waiting_review"
            and run.stage_status in REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES
            and current_stage == run.current_stage
            and current_stage in REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES
        )
        is_final_stage = (
            run.status == RunStatus.SUCCESS.value
            and current_stage == REQUIREMENT_ANALYSIS_FINAL_STAGE
            and run.current_stage in REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES
        )
        if not is_review_stage and not is_final_stage:
            raise ErrBadRequest

        revision_instruction = str(
            body.get(REVISION_INSTRUCTION_FIELD) or body.get("revision_instruction") or ""
        ).strip()
        if not revision_instruction:
            raise ErrBadRequest

        latest_task = await self.repository.get_latest_worker_task_by_run_id(run.run_id)
        if latest_task is None:
            raise ErrBadRequest

        if "configJson" in body:
            run.config_json = normalize_config_json(body.get("configJson"))
        elif not isinstance(run.config_json, dict):
            run.config_json = normalize_config_json(run.config_json)
        if is_final_stage:
            result_yaml = str(body.get("resultYaml") or run.result_yaml or "").strip()
            if not result_yaml:
                raise ErrBadRequest
            run.config_json["resultYaml"] = str(body.get("resultYaml") or run.result_yaml or "")
        run.config_json[REVISION_INSTRUCTION_FIELD] = revision_instruction
        run.status = RunStatus.PENDING.value
        if is_final_stage:
            run.current_stage = REQUIREMENT_ANALYSIS_FINAL_STAGE
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        self.repository.add(
            WorkerTask(
                domain="ai",
                task_id=new_id(),
                task_type=task_type_for("requirement_analysis"),
                run_id=run.run_id,
                generate_task_id=run.task_id,
                llm_connection_id=await self.stage_connection(
                    run, body or {}, user_id, latest_task.llm_connection_id
                ),
                status=RunStatus.PENDING.value,
            )
        )
        run._operation = "revise"
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def revise_function_case_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        await self.owned_run(user_id, run_id, "function", action="execute")
        # Refresh under the row lock to observe any concurrent submission.
        run = await self.repository.get_run_for_update(run_id)
        if run is None:
            raise ErrNotFound
        # The locked reload may return a new instance without the transient actor.
        run._actor = user_id
        stage = str(body.get("stage") or body.get("currentStage") or "")
        is_checkpoint = (
            run.checkpoint_enabled
            and run.status == "waiting_review"
            and run.stage_status in FUNCTION_CASE_REVIEW_READY_STATUSES
            and stage == run.current_stage
            and stage in FUNCTION_CASE_REVIEWABLE_STAGES
        )
        is_final = (
            stage == "detailed_cases"
            and run.current_stage in {"detailed_cases", "completed", ""}
            and run.status == RunStatus.SUCCESS.value
        )
        if (
            not (is_checkpoint or is_final)
            or run.review_status != ReviewStatus.PENDING.value
            or run.import_status == ImportStatus.IMPORTED.value
        ):
            raise ErrBadRequest
        instruction = str(body.get("revisionInstruction") or "").strip()
        if not instruction:
            raise ErrBadRequest
        config = dict(normalize_config_json(run.config_json))
        field = {"requirement_analysis": "requirementAnalysis", "case_names": "caseNames"}.get(
            stage
        )
        if field and "configJson" in body:
            edits = normalize_function_stage_config(stage, body["configJson"])
            # Confirmed upstream inputs cannot be edited by a revision request.
            if field not in edits:
                raise ErrBadRequest
            config[field] = edits[field]
        if field:
            current_output = config.get(field)
            if not current_output or (
                isinstance(current_output, str) and not current_output.strip()
            ):
                raise ErrBadRequest
        else:
            current_output = str(body.get("resultYaml", run.result_yaml) or "")
            if not current_output.strip():
                raise ErrBadRequest
            cases = generated_function_cases(SimpleNamespace(result_yaml=current_output))
            if not cases:
                raise ErrBadRequest
            validate_function_candidate_cases(cases)
            config["resultYaml"] = json.dumps({"cases": cases}, ensure_ascii=False)
        latest_task = await self.repository.get_latest_worker_task_by_run_id(run_id)
        if latest_task is None:
            raise ErrBadRequest
        config[REVISION_INSTRUCTION_FIELD] = instruction
        run.config_json = config
        if is_final:
            run.result_yaml = current_output
        run.status = RunStatus.PENDING.value
        run.current_stage = stage
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        self.repository.add(
            WorkerTask(
                domain="ai",
                task_id=new_id(),
                task_type=task_type_for("function"),
                run_id=run.run_id,
                generate_task_id=run.task_id,
                llm_connection_id=await self.stage_connection(
                    run, body or {}, user_id, latest_task.llm_connection_id
                ),
                status=RunStatus.PENDING.value,
            )
        )
        run._operation = "revise"
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def review_stage(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, "function", action="review")
        if (
            not run.checkpoint_enabled
            or run.status != "waiting_review"
            or run.stage_status not in FUNCTION_CASE_REVIEW_READY_STATUSES
        ):
            raise ErrBadRequest

        current_stage = str(body.get("currentStage") or body.get("stage") or "")
        if (
            current_stage != run.current_stage
            or current_stage not in FUNCTION_CASE_REVIEWABLE_STAGES
        ):
            raise ErrBadRequest

        action = str(
            body.get("action")
            or body.get("reviewStatus")
            or body.get("status")
            or body.get("stageStatus")
            or "approve"
        )
        if action == "approved":
            action = "approve"
        if action == "rejected":
            action = "reject"

        if action == "approve":
            latest_task = await self.repository.get_latest_worker_task_by_run_id(run.run_id)
            next_stage = next_function_case_stage(run.current_stage)
            if latest_task is None or next_stage is None:
                raise ErrBadRequest
            run.status = RunStatus.PENDING.value
            run.current_stage = next_stage
            run.stage_status = StageStatus.PENDING.value
            run.error_message = ""
            self.repository.add(
                WorkerTask(
                    domain="ai",
                    task_id=new_id(),
                    task_type=task_type_for("function"),
                    run_id=run.run_id,
                    generate_task_id=run.task_id,
                    llm_connection_id=await self.stage_connection(
                        run, body or {}, user_id, latest_task.llm_connection_id
                    ),
                    status=RunStatus.PENDING.value,
                )
            )
        elif action == "reject":
            run.status = RunStatus.CANCELED.value
            run.stage_status = StageStatus.FAILED.value
        else:
            raise ErrBadRequest
        run._stage_review = (
            current_stage,
            "approved" if action == "approve" else "rejected",
            str(body.get("reviewComment") or body.get("comment") or ""),
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def retry_stage(
        self,
        run_id: str,
        body: dict[str, Any] | None,
        user_id: str,
        *,
        kind: str = "function",
    ) -> dict:
        await self.owned_run(user_id, run_id, kind, action="execute")
        run = await self.repository.get_run_for_update(run_id)
        if run is None:
            raise ErrNotFound
        # The locked reload may return a new instance without the transient actor.
        run._actor = user_id
        allowed_stages = (
            {*REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES, REQUIREMENT_ANALYSIS_FINAL_STAGE}
            if kind == "requirement_analysis"
            else {*FUNCTION_CASE_REVIEWABLE_STAGES, "detailed_cases"}
        )
        payload = body or {}
        stage = str(payload.get("stage") or payload.get("currentStage") or run.current_stage)
        if (
            run.status not in {"failed", "error"}
            # Older retries changed only this field without enqueueing a task.
            or run.stage_status not in {"failed", "retrying"}
            or stage != run.current_stage
            or stage not in allowed_stages
            or run.review_status != ReviewStatus.PENDING.value
            or run.import_status == ImportStatus.IMPORTED.value
        ):
            raise ErrBadRequest
        latest_task = await self.repository.get_latest_worker_task_by_run_id(run_id)
        if latest_task is None or latest_task.status in {"pending", "claimed", "running"}:
            raise ErrBadRequest
        # Retain upstream outputs and any failed revision's instruction for this attempt.
        run.status = RunStatus.PENDING.value
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        self.repository.add(
            WorkerTask(
                domain="ai",
                task_id=new_id(),
                task_type=task_type_for(kind),
                run_id=run.run_id,
                generate_task_id=run.task_id,
                llm_connection_id=await self.stage_connection(
                    run, body or {}, user_id, latest_task.llm_connection_id
                ),
                status=RunStatus.PENDING.value,
            )
        )
        run._operation = "retry"
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def generate_relation_analysis(
        self, run_id: str, body: dict[str, Any] | None, user_id: str
    ) -> dict:
        """审核通过后按用户触发派发图谱分析；重复点击基于最新用例重新生成。"""

        await self.owned_run(user_id, run_id, "function", action="execute")
        run = await self.repository.get_run_for_update(run_id)
        if run is None:
            raise ErrNotFound
        # The locked reload may return a new instance without the transient actor.
        run._actor = user_id
        if (
            run.current_stage == FUNCTION_CASE_RELATION_STAGE
            and run.status in FUNCTION_CASE_RELATION_DISPATCH_STATUSES
        ):
            raise dynamic_error(ErrBadRequest, "图谱正在生成中，请等待完成后再试")
        if run.review_status != ReviewStatus.APPROVED.value:
            raise dynamic_error(ErrBadRequest, "候选结果审核通过后才能生成图谱")
        if not (
            run.status == RunStatus.SUCCESS.value
            or (
                run.status in {"failed", "error"}
                and run.current_stage == FUNCTION_CASE_RELATION_STAGE
            )
        ):
            raise ErrBadRequest
        latest_task = await self.repository.get_latest_worker_task_by_run_id(run_id)
        if latest_task is None or latest_task.status in FUNCTION_CASE_RELATION_DISPATCH_STATUSES:
            raise ErrBadRequest
        cases = generated_function_cases(run)
        if not cases:
            raise ErrBadRequest
        case_ids = [str(first_present(case, "case_id", "caseId") or "").strip() for case in cases]
        if any(not case_id for case_id in case_ids):
            raise dynamic_error(
                ErrBadRequest, "用例缺少平台签发的 case_id，请重新生成用例后再生成图谱"
            )
        if len(case_ids) != len(set(case_ids)):
            raise dynamic_error(ErrBadRequest, "用例 case_id 重复，请重新生成用例后再生成图谱")
        config = dict(normalize_config_json(run.config_json))
        config.pop(REVISION_INSTRUCTION_FIELD, None)
        # 上一次关系产物随 config 进入派发快照，skill 据此沿用既有流程/节点/连线 ID。
        config["resultYaml"] = json.dumps({"cases": cases}, ensure_ascii=False)
        run.config_json = config
        run.status = RunStatus.PENDING.value
        run.current_stage = FUNCTION_CASE_RELATION_STAGE
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        self.repository.add(
            WorkerTask(
                domain="ai",
                task_id=new_id(),
                task_type=task_type_for("function"),
                run_id=run.run_id,
                generate_task_id=run.task_id,
                llm_connection_id=await self.stage_connection(
                    run, body or {}, user_id, latest_task.llm_connection_id
                ),
                status=RunStatus.PENDING.value,
            )
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)
