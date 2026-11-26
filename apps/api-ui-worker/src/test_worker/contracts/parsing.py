"""Single parsers for UI tasks, snapshots and control-plane snapshot wrappers.

Control-plane responses allow additive fields. These parsers read only the
declared protocol keys, ignore unknown fields, and apply the existing defaults
for missing values. Polling and offline ``once`` mode both use this module so a
snapshot shape cannot silently diverge between the two entry points.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .types import (
    ScreenshotPolicy,
    UiCaseRunSnapshot,
    UiCaseSnapshot,
    UiStepDefinition,
    UiSuiteRunItemSnapshot,
    UiSuiteSnapshot,
    UiTaskType,
    UiTestSuiteRunSnapshot,
    UiWorkerTask,
    UiWorkerTaskSnapshotResponse,
)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _ui_task_type(value: object) -> UiTaskType:
    return "suite_run" if value == "suite_run" else "case_debug"


def parse_ui_task(data: Mapping[str, Any]) -> UiWorkerTask:
    """Parse a UI claim response into the single task model."""
    return UiWorkerTask(
        task_id=str(data.get("taskId", "")),
        task_type=_ui_task_type(data.get("taskType")),
        run_id=str(data.get("runId", "")),
        suite_id=str(data.get("suiteId", "")),
        case_id=str(data.get("caseId", "")),
        lease_seconds=int(data.get("leaseSeconds", 0) or 0),
    )


def parse_snapshot_response(
    data: Mapping[str, Any],
    *,
    default_task_id: str = "",
    default_screenshot_policy: ScreenshotPolicy | None = None,
) -> UiWorkerTaskSnapshotResponse:
    """Parse the response returned by the UI snapshot endpoint."""
    task_type = _ui_task_type(data.get("taskType"))
    case_run = None
    suite_run = None
    if task_type == "case_debug" and isinstance(data.get("caseRun"), Mapping):
        case_run = parse_case_run_snapshot(
            _mapping(data["caseRun"]),
            default_task_id=default_task_id,
            default_screenshot_policy=default_screenshot_policy,
        )
    elif task_type == "suite_run" and isinstance(data.get("suiteRun"), Mapping):
        suite_run = parse_suite_run_snapshot(
            _mapping(data["suiteRun"]),
            default_task_id=default_task_id,
            default_screenshot_policy=default_screenshot_policy,
        )
    return UiWorkerTaskSnapshotResponse(
        task_type=task_type,
        case_run=case_run,
        suite_run=suite_run,
    )


def parse_case_run_snapshot(
    data: Mapping[str, Any] | None,
    *,
    default_task_id: str = "",
    default_screenshot_policy: ScreenshotPolicy | None = None,
) -> UiCaseRunSnapshot | None:
    """Parse a case snapshot, ignoring unknown control-plane fields."""
    if not data:
        return None

    case_data = _mapping(data.get("case"))
    steps = _parse_steps(case_data)
    case = UiCaseSnapshot(
        case_id=str(case_data.get("caseId", "")),
        name=str(case_data.get("name", "")),
        suite_id=case_data.get("suiteId"),
        description=case_data.get("description"),
        enabled=case_data.get("enabled"),
        order_no=case_data.get("orderNo"),
        steps_json=case_data.get("stepsJson"),
        steps=steps,
    )
    return UiCaseRunSnapshot(
        task_id=str(data.get("taskId") or default_task_id or ""),
        run_id=str(data.get("runId") or ""),
        case=case,
        suite=_parse_suite(data, default_screenshot_policy),
    )


def parse_suite_run_snapshot(
    data: Mapping[str, Any] | None,
    *,
    default_task_id: str = "",
    default_screenshot_policy: ScreenshotPolicy | None = None,
) -> UiTestSuiteRunSnapshot | None:
    """Parse a suite snapshot, ignoring unknown control-plane fields."""
    if not data:
        return None

    items = []
    for item_data in data.get("items", []):
        item = _mapping(item_data)
        case_data = _mapping(item.get("case"))
        items.append(
            UiSuiteRunItemSnapshot(
                item_id=str(item.get("itemId", "")),
                continue_on_failure=bool(item.get("continueOnFailure", False)),
                case=UiCaseSnapshot(
                    case_id=str(case_data.get("caseId", "")),
                    name=str(case_data.get("name", "")),
                    suite_id=case_data.get("suiteId"),
                    description=case_data.get("description"),
                    enabled=case_data.get("enabled"),
                    order_no=case_data.get("orderNo"),
                    steps_json=case_data.get("stepsJson"),
                    steps=_parse_steps(case_data),
                ),
            )
        )
    return UiTestSuiteRunSnapshot(
        task_id=str(data.get("taskId") or default_task_id or ""),
        run_id=str(data.get("runId") or data.get("suiteRunId") or ""),
        items=items,
        suite=_parse_suite(data, default_screenshot_policy),
    )


def parse_step_definition(raw: Mapping[str, Any], index: int) -> UiStepDefinition:
    """Read one camelCase step payload; ``index`` is its 1-based position in messages."""
    save_to = raw.get("saveTo")
    if save_to is not None and (
        not isinstance(save_to, list)
        or not all(isinstance(item, dict) for item in save_to)
    ):
        raise ValueError(f"步骤 {index} 的 saveTo 必须是对象数组")
    return UiStepDefinition(
        keyword=str(raw.get("keyword") or ""),
        order_no=raw.get("orderNo"),
        step_name=raw.get("stepName"),
        locator_type=raw.get("locatorType"),
        locator_value=raw.get("locatorValue"),
        operation_value=raw.get("operationValue"),
        expect_value=raw.get("expectValue"),
        timeout_ms=raw.get("timeoutMs"),
        continue_on_failure=raw.get("continueOnFailure"),
        enabled=raw.get("enabled"),
        description=raw.get("description"),
        comparator=raw.get("comparator"),
        save_to=save_to,
    )


def _parse_steps(case_data: Mapping[str, Any]) -> list[UiStepDefinition] | None:
    raw_steps = case_data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None
    return [
        parse_step_definition(raw, index)
        for index, raw in enumerate(raw_steps, 1)
        if isinstance(raw, Mapping)
    ]


def _parse_suite(
    data: Mapping[str, Any], default_screenshot_policy: ScreenshotPolicy | None
) -> UiSuiteSnapshot | None:
    suite_data = _mapping(data.get("suite"))
    if not suite_data:
        return None
    return UiSuiteSnapshot(
        suite_id=str(suite_data.get("suiteId", "")),
        name=str(suite_data.get("name", "")),
        headless=suite_data.get("headless"),
        slow_mo_ms=suite_data.get("slowMoMs"),
        viewport_width=suite_data.get("viewportWidth"),
        viewport_height=suite_data.get("viewportHeight"),
        default_step_timeout_ms=suite_data.get("defaultStepTimeoutMs"),
        screenshot_policy=suite_data.get("screenshotPolicy", default_screenshot_policy),
    )
