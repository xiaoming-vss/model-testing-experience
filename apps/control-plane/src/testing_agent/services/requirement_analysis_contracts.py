"""Version-aware validation at worker, review, edit and import boundaries."""

import json

from testing_agent.core.enums import ReviewStatus
from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.requirement_artifacts import serialize_artifact, validate_artifact


def ensure_requirement_run_mutable(review_status: str | None) -> None:
    """Rejected candidate runs are terminal; generation must start a new run."""
    if review_status == ReviewStatus.REJECTED.value:
        raise dynamic_error(ErrBadRequest, "该运行已拒绝，仅支持查看或删除，请重新运行任务")


def artifact(value, kind, *, allow_resolved_questions=False):
    try:
        return validate_artifact(value, kind, allow_resolved_questions=allow_resolved_questions)
    except ValueError as exc:
        raise dynamic_error(ErrBadRequest, str(exc)) from exc


def validate_run_output(
    run, *, config=None, result=None, final=False, allow_resolved_questions=False
):
    snapshot = getattr(run, "snapshot_json", None) or {}
    if snapshot.get("workflowVersion", 2) != 2:
        raise dynamic_error(ErrBadRequest, "不支持的需求分析工作流版本")
    config = config if config is not None else run.config_json or {}
    if not isinstance(config, dict):
        raise dynamic_error(ErrBadRequest, "configJson 必须是对象")
    if "secondStepOutput" in config:
        raise dynamic_error(ErrBadRequest, "两阶段任务不接受独立流程稿产物")
    artifact(
        config.get("firstStepOutput"),
        "document_extraction",
        allow_resolved_questions=final or allow_resolved_questions,
    )
    if final:
        artifact(
            result if result is not None else run.result_yaml,
            "requirement_understanding",
            allow_resolved_questions=allow_resolved_questions,
        )


def merge_stage_config(run, edits, stage, *, allow_resolved_questions=False):
    """Permit editing the active extraction only; preserve all confirmed upstream inputs."""
    current = dict(run.config_json or {})
    if not isinstance(edits, dict):
        raise dynamic_error(ErrBadRequest, "configJson 必须是对象")
    allowed = "firstStepOutput" if stage == "extracting_text" else None
    for key, value in edits.items():
        if key != allowed and (key not in current or current[key] != value):
            raise dynamic_error(ErrBadRequest, "不能修改已确认的上游或其他阶段产物")
    merged = {**current, **edits}
    merged["firstStepOutput"] = artifact(
        merged.get("firstStepOutput"),
        "document_extraction",
        allow_resolved_questions=stage != "extracting_text" or allow_resolved_questions,
    )
    return merged


def imported_content(run):
    validate_run_output(run, final=True)
    return serialize_artifact(run.result_yaml, "requirement_understanding")


def normalize_requirement_config(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, "configJson 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise dynamic_error(ErrBadRequest, "configJson 必须是对象")
    return value
