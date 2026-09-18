"""Normalize UI case step payloads at the runner boundary."""

from __future__ import annotations

from ..contracts.types import UiCaseSnapshot, UiStepDefinition


def normalize_case_steps(case: UiCaseSnapshot) -> list[UiStepDefinition]:
    """Prefer explicit steps and fall back to the camelCase stepsJson payload."""
    if case.steps:
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
        )
        for step in steps_json
    ]
