from __future__ import annotations

import builtins
import json
from hashlib import sha256
from types import SimpleNamespace
from typing import Any

import yaml

from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
)
from testing_agent.domain.ai_tasks import DEFAULT_FUNCTION_CASE_MODULE
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.schemas.requirement import normalize_document_type
from testing_agent.services.functional_requirement_source import functional_requirement_source
from testing_agent.services.import_payload import import_items, parse_import_payload
from testing_agent.services.standalone_run import StandaloneRun
from testing_agent.services.ui_test_case import ui_import_cases


def dump_task(task: AiGenerateTask) -> dict[str, Any]:
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
        "instruction": task.instruction,
        "createdAt": task.created_at,
        "updatedAt": task.updated_at,
    }


def dump_run(run: StandaloneRun) -> dict[str, Any]:
    summary = run.result_summary_json or {}
    if isinstance(summary, dict) and isinstance(summary.get("uiSemanticReview"), dict):
        review = summary["uiSemanticReview"]
        digest = sha256((run.result_yaml or "").encode("utf-8")).hexdigest()
        if review.get("artifactSha256") != digest:
            # Derive staleness without rewriting the historical report or attempt ledger.
            summary = {**summary, "uiSemanticReview": {**review, "status": "stale"}}
    return {
        "createdAt": run.created_at,
        "startedAt": run.started_at,
        "finishedAt": run.finished_at,
        "updatedAt": run.history_updated_at,
        "hasResult": bool(run.result_yaml),
        "availableArtifacts": [
            key
            for key in (
                "requirementAnalysis",
                "caseNames",
                "caseRelations",
                "firstStepOutput",
                "uiSurface",
                "uiDesign",
            )
            if isinstance(run.config_json, dict) and run.config_json.get(key)
        ],
        "runId": run.run_id,
        "taskId": run.task_id,
        "requirementId": run.requirement_id,
        "sprintId": run.sprint_id,
        "projectId": run.project_id,
        "triggerUserId": run.trigger_user_id,
        "triggerType": run.trigger_type,
        "status": run.status,
        "workflowVersion": (run.snapshot_json or {}).get("workflowVersion", 2),
        "checkpointEnabled": run.checkpoint_enabled,
        "generationChainManaged": bool((run.snapshot_json or {}).get("generationChainManaged")),
        "currentStage": run.current_stage,
        "stageStatus": run.stage_status,
        "snapshotJson": run.snapshot_json or {},
        "errorMessage": run.error_message,
        "configJson": run.config_json or {},
        "resultYaml": run.result_yaml,
        "resultSummaryJson": summary,
        "reviewStatus": run.review_status,
        "importStatus": run.import_status,
        "importedTargets": run.imported_targets or [],
        "importedAt": run.imported_at,
        "reviewerUserId": run.reviewer_user_id,
        "reviewedAt": run.reviewed_at,
        "reviewComment": run.review_comment,
        "durationMs": run.duration_ms,
    }


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


async def build_generate_run_snapshot(
    repository: AiGenerateTaskRepository,
    kind: str,
    task: AiGenerateTask,
    run_id: str,
    instruction: str | None = None,
    worker_task_id: str | None = None,
    material_version_id: str = "",
) -> dict[str, Any]:
    source_content = task.source_content
    document_type = ""
    document_download_url = ""
    uses_requirement_document = False
    functional_source: dict[str, Any] = {}
    if kind == "function" and task.requirement_id:
        functional_source = await functional_requirement_source(
            GenerationChainRepository(repository.session),
            task.requirement_id,
            material_version_id,
        )
        source_content = functional_source["sourceContent"]
    elif kind == "requirement_analysis":
        requirement = await repository.get_requirement(task.requirement_id)
        if requirement is not None:
            uses_requirement_document = True
            document_type = normalize_document_type(str(requirement.document_type or "richtext"))
            document_download_url = (
                worker_requirement_document_download_url(worker_task_id)
                if worker_task_id
                else requirement_document_download_url(requirement, str(task.requirement_id or ""))
            )
            source_content = str(getattr(requirement, "document_content", "") or "")
            if not source_content and (
                document_type == "docx" or bool(getattr(requirement, "document_file_id", ""))
            ):
                source_content = document_download_url
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
        snapshot["documentFilename"] = str(getattr(requirement, "document_filename", "") or "")
        snapshot["documentFileId"] = str(getattr(requirement, "document_file_id", "") or "")
        snapshot["documentHash"] = str(getattr(requirement, "document_hash", "") or "")
    else:
        snapshot["sourceType"] = task.source_type
    snapshot.update(functional_source)
    return snapshot


def generated_payload(run: Any, content: str | None = None) -> dict[str, Any]:
    raw = (run.result_yaml or "") if content is None else content
    if not raw.strip():
        raise ErrBadRequest()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ErrBadRequest() from exc
    return parse_import_payload(data)


def generated_function_cases(run: Any, content: str | None = None) -> builtins.list[dict[str, Any]]:
    payload = generated_payload(run, content)
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
        raise ErrBadRequest()
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
            raise ErrBadRequest()
        names.add(key)
        normalized_cases.append(case)
    return normalized_cases


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
            raise ErrBadRequest() from exc
        if isinstance(parsed, dict):
            return parsed
    raise ErrBadRequest()


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


def validate_ui_candidate_cases(result_yaml: str) -> builtins.list[dict[str, Any]]:
    payload = generated_payload(SimpleNamespace(result_yaml=result_yaml))
    try:
        cases = ui_import_cases(payload)
    except AppError as exc:
        raise ErrBadRequest() from exc
    if not cases:
        raise ErrBadRequest()
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
            raise ErrBadRequest()
        for step in case["stepsJson"]:
            if (
                not isinstance(step, dict)
                or not isinstance(step.get("keyword"), str)
                or not step["keyword"].strip()
            ):
                raise ErrBadRequest()
    return cases
