from __future__ import annotations

import builtins
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
)
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.requirement import normalize_document_type
from testing_agent.services.ai_task_contracts import DEFAULT_FUNCTION_CASE_MODULE
from testing_agent.services.api_import_payload import (
    import_items,
    parse_import_payload,
)
from testing_agent.services.ui_test_case import ui_import_cases


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
