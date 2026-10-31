"""Normalize UI case step payloads at the runner boundary."""

from __future__ import annotations

from typing import Any

from ..contracts.types import UiCaseSnapshot, UiStepDefinition


def _normalize_save_to(raw: Any, index: int) -> list[dict[str, Any]] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError(f"步骤 {index} 的 saveTo 必须是对象数组")
    return raw


def normalize_case_steps(case: UiCaseSnapshot) -> list[UiStepDefinition]:
    """Prefer explicit steps and fall back to the camelCase stepsJson payload."""
    # Check raw metadata before normalization can discard it, even when explicit steps win.
    raw_steps = case.steps_json if isinstance(case.steps_json, list) else []
    for index, raw in enumerate(raw_steps, 1):
        if isinstance(raw, dict) and {
            "dataBindings",
            "sourceRefs",
        }.intersection(raw):
            raise ValueError(
                f"步骤 {index} 仍含补全草稿元数据，请先补齐并导入，禁止直接执行"
            )
        if isinstance(raw, dict) and "missingFields" in raw:
            pending = raw["missingFields"]
            if not isinstance(pending, list) or pending:
                raise ValueError(f"步骤 {index} 的 missingFields 尚未补齐，禁止执行")
    if case.steps:
        for index, step in enumerate(case.steps, 1):
            if step.missing_fields:
                raise ValueError(f"步骤 {index} 的 missingFields 尚未补齐，禁止执行")
        return case.steps

    steps_json = case.steps_json
    if steps_json is not None and not isinstance(steps_json, list):
        raise ValueError("case.steps_json 必须是数组")
    if not steps_json:
        return []

    if not all(isinstance(step, dict) for step in steps_json):
        raise ValueError("case.steps_json 的每个步骤必须是对象")

    return [
        UiStepDefinition(
            keyword=step.get("keyword", ""),
            order_no=step.get("orderNo"),
            step_name=step.get("stepName"),
            locator_type=step.get("locatorType"),
            locator_value=step.get("locatorValue"),
            operation_value=step.get("operationValue"),
            expect_value=step.get("expectValue"),
            timeout_ms=step.get("timeoutMs"),
            continue_on_failure=step.get("continueOnFailure"),
            enabled=step.get("enabled"),
            description=step.get("description"),
            comparator=step.get("comparator"),
            save_to=_normalize_save_to(step.get("saveTo"), index),
        )
        for index, step in enumerate(steps_json, 1)
    ]
