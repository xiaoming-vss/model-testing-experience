"""Functional task progress and result summary builders."""

from __future__ import annotations

import json

from testing_agent_ai_worker.models.execution import TaskProgress, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.tasks.result_summary import build_task_result_summary


def build_progress(
    task: Task,
    *,
    current_stage: str,
    stage_status: str,
    requirement_analysis_json: str,
    case_names_json: str,
    detailed_cases_json: str,
    relations_json: str = "",
) -> TaskProgress:
    """构造功能任务的阶段性 progress 快照。"""

    config_json = build_config_json(
        requirement_analysis_json=requirement_analysis_json,
        case_names_json=case_names_json,
        relations_json=relations_json,
    )
    return TaskProgress(
        task_id=task.task_id,
        run_id=task.run_id,
        current_stage=current_stage,
        stage_status=stage_status,
        intermediate_json_text=""
        if current_stage == "detailed_cases" and stage_status == "running"
        else config_json,
        output_yaml="",
        result_summary_json=build_result_summary_json(
            task=task,
            status="running",
            config_json=config_json,
            detailed_cases_json=detailed_cases_json,
            error_message=None,
        ),
    )


def build_config_json(
    *,
    requirement_analysis_json: str,
    case_names_json: str,
    relations_json: str = "",
) -> str:
    """统一构造功能任务的 `configJson` 结构。"""

    return json.dumps(
        {
            "requirementAnalysis": parse_optional_json(requirement_analysis_json),
            "caseNames": parse_optional_json(case_names_json),
            "caseRelations": parse_optional_json(relations_json),
        },
        ensure_ascii=False,
        indent=2,
    )


def build_result_summary_json(
    *,
    task: Task,
    status: TaskStatus | str,
    config_json: str,
    detailed_cases_json: str,
    error_message: str | None,
    relations_json: str = "",
) -> str:
    """构造平台展示用摘要 JSON。"""

    document_type = (task.payload.document_type or task.payload.source_type or "").strip().lower()
    return build_task_result_summary(
        task=task,
        status=status,
        error_message=error_message,
        details={
            "documentType": document_type,
            "sourceType": document_type,
            "caseCount": count_cases(detailed_cases_json),
            "configJsonLength": len(config_json),
            "resultLength": len(detailed_cases_json),
            **relation_summary_stats(relations_json),
        },
    )


def relation_summary_stats(relations_json: str) -> dict[str, int]:
    """从 2.0 关系产物中提取展示统计，非 JSON 或空产物不产生统计。"""

    parsed = parse_optional_json(relations_json)
    if not isinstance(parsed, dict):
        return {}
    main_paths = parsed.get("main_paths")
    edges = parsed.get("edges")
    if not isinstance(main_paths, list) and not isinstance(edges, list):
        return {}
    stats: dict[str, int] = {}
    if isinstance(main_paths, list):
        stats["mainPathCount"] = len(main_paths)
    if isinstance(edges, list):
        stats["edgeCount"] = len(edges)
    referenced: set[str] = set()
    if isinstance(main_paths, list):
        for path in main_paths:
            if isinstance(path, dict) and isinstance(path.get("case_ids"), list):
                referenced.update(cid for cid in path["case_ids"] if isinstance(cid, str))
    if isinstance(edges, list):
        for edge in edges:
            if isinstance(edge, dict):
                referenced.update(
                    edge[key] for key in ("from_case_id", "to_case_id") if isinstance(edge.get(key), str)
                )
    if referenced:
        stats["linkedCaseCount"] = len(referenced)
    return stats


def parse_optional_json(raw_json_text: str):
    normalized = raw_json_text.strip()
    if not normalized:
        return None
    return json.loads(normalized)


def count_cases(detailed_cases_json: str) -> int:
    if not detailed_cases_json.strip():
        return 0
    try:
        parsed = json.loads(detailed_cases_json)
    except json.JSONDecodeError:
        return 0
    if not isinstance(parsed, dict):
        return 0
    cases = parsed.get("cases", [])
    if not isinstance(cases, list):
        return 0
    return len(cases)
