"""Validate one UI artifact without changing confirmed upstream inputs."""

from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.ui_completion import compile_case
from testing_agent.domain.ui_generation_artifacts import (
    UI_FIELDS,
    UI_WORKFLOW_VERSION,
    object_value,
    validate_design,
    validate_surface,
)
from testing_agent.services.ui_test_case import validate_ui_import_payload


def is_ui_workflow(run: Any) -> bool:
    return (getattr(run, "snapshot_json", None) or {}).get(
        "uiWorkflowVersion"
    ) == UI_WORKFLOW_VERSION


def validate_ui_yaml(raw: str) -> None:
    import yaml

    from testing_agent.domain.ui_generation_missing_fields import draft_step_for_validation

    try:
        cases = yaml.safe_load(raw)
        if not isinstance(cases, list):
            raise ValueError("UI YAML 必须是列表")
        if not cases:
            return  # Every business goal may have been explicitly excluded in the design.
        normalized = []
        for case in cases:
            case = compile_case(case, for_validation=True)
            if not isinstance(case, dict) or not isinstance(case.get("stepsJson"), list):
                raise ValueError("UI 用例需要 stepsJson 数组")
            steps = []
            for step in case["stepsJson"]:
                if not isinstance(step, dict):
                    raise ValueError("UI 步骤必须是对象")
                value = draft_step_for_validation(step)
                value.pop("missingFields", None)
                steps.append(value)
            normalized.append({**case, "stepsJson": steps})
        validate_ui_import_payload({"items": normalized})
    except (ValueError, TypeError, yaml.YAMLError) as exc:
        raise dynamic_error(ErrBadRequest, "UI YAML 草稿不合法：" + str(exc)) from exc


def validate_ui_output(run: Any, stage: str, value: Any) -> Any:
    cases = (run.snapshot_json or {}).get("functionalCases", [])
    if not isinstance(cases, list) or not cases:
        raise dynamic_error(ErrBadRequest, "运行缺少正式功能用例快照")
    try:
        if stage == "ui_surface":
            return validate_surface(value, cases)
        if stage == "ui_design":
            return validate_design(value, cases)
        if stage == "ui_yaml":
            import yaml

            parsed = yaml.safe_load(value)
            if isinstance(parsed, list) and any(
                isinstance(case, dict) and "draftVersion" in case for case in parsed
            ):
                value = yaml.safe_dump(
                    [compile_case(case) for case in parsed], allow_unicode=True, sort_keys=False
                )
            validate_ui_yaml(value)
            return value
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise dynamic_error(ErrBadRequest, "阶段产物不合法：" + str(exc)) from exc
    raise ErrBadRequest()


def validate_ui_worker_output(run: Any, stage: str, config: Any, result: Any = None) -> dict:
    try:
        data = object_value(config)
        existing = object_value(run.config_json or {})
    except (ValueError, TypeError) as exc:
        raise dynamic_error(ErrBadRequest, "configJson 必须是对象") from exc
    transient = {"revisionInstruction", "resultYaml"}
    current_field = UI_FIELDS.get(stage)
    allowed = transient | ({current_field} if current_field else set())
    if {k: v for k, v in data.items() if k not in allowed} != {
        k: v for k, v in existing.items() if k not in allowed
    }:
        raise dynamic_error(ErrBadRequest, "Worker 不得修改已确认的上游产物或运行上下文")
    for other, field in UI_FIELDS.items():
        if other != stage and data.get(field) != existing.get(field):
            raise dynamic_error(ErrBadRequest, "Worker 不得修改或丢失已确认的上游产物")
    if stage in UI_FIELDS:
        data[UI_FIELDS[stage]] = validate_ui_output(run, stage, data.get(UI_FIELDS[stage]))
        if result and str(result).strip():
            raise ErrBadRequest()
    else:
        validate_ui_output(run, stage, result)
    return data
