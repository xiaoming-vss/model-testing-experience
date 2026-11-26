from __future__ import annotations

import builtins
import json
from typing import Any

import yaml

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.ai_tasks import DEFAULT_FUNCTION_CASE_MODULE
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.services.import_payload import import_items, parse_import_payload


def _task_payload(task: AiGenerateTask, *, include_source: bool) -> dict[str, Any]:
    payload = {
        "taskId": task.task_id,
        "taskType": task.task_type,
        "name": task.name,
        "projectId": task.project_id,
        "sprintId": task.sprint_id,
        "requirementId": task.requirement_id,
        "creatorUserId": task.creator_user_id,
        "sourceType": task.source_type,
        "interfaceIds": list(getattr(task, "interface_ids_json", None) or []),
        "instruction": task.instruction,
        "createdAt": task.created_at,
        "updatedAt": task.updated_at,
    }
    if include_source:
        payload["sourceContent"] = task.source_content
    return payload


def dump_task(task: AiGenerateTask) -> dict[str, Any]:
    return _task_payload(task, include_source=True)


def dump_task_summary(task: AiGenerateTask, latest_run_status: str = "") -> dict[str, Any]:
    """List payload without the potentially large source body."""
    payload = _task_payload(task, include_source=False)
    payload["interfaceCount"] = len(getattr(task, "interface_ids_json", None) or [])
    payload["latestRunStatus"] = latest_run_status
    return payload


def generated_payload(content: str) -> dict[str, Any]:
    if not content.strip():
        raise ErrBadRequest()
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ErrBadRequest() from exc
    return parse_import_payload(data)


def generated_function_cases(content: str) -> builtins.list[dict[str, Any]]:
    payload = generated_payload(content)
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
