from __future__ import annotations

import pytest

from test_worker.contracts.types import (
    UiCaseRunSnapshot,
    UiCaseSnapshot,
    UiStepDefinition,
    UiSuiteRunItemSnapshot,
)
from test_worker.ui.case_runner import _normalize_steps as normalize_case_steps
from test_worker.ui.suite_runner import _normalize_steps as normalize_suite_steps


def case_snapshot(steps_json: object) -> UiCaseSnapshot:
    return UiCaseSnapshot(
        case_id="case-1",
        name="Login",
        steps_json=steps_json,  # type: ignore[arg-type]
    )


def test_case_runner_uses_steps_json_array() -> None:
    snapshot = UiCaseRunSnapshot(
        task_id="task-1",
        run_id="run-1",
        case=case_snapshot([{"orderNo": 1, "keyword": "open"}]),
    )

    steps = normalize_case_steps(snapshot)

    assert [(step.order_no, step.keyword) for step in steps] == [(1, "open")]


def test_suite_runner_uses_steps_json_array() -> None:
    item = UiSuiteRunItemSnapshot(
        item_id="item-1",
        continue_on_failure=False,
        case=case_snapshot([{"orderNo": 1, "keyword": "click"}]),
    )

    steps = normalize_suite_steps(item)

    assert [(step.order_no, step.keyword) for step in steps] == [(1, "click")]


@pytest.mark.parametrize("normalize", [normalize_case_steps, normalize_suite_steps])
def test_runner_rejects_steps_json_string(normalize) -> None:
    case = case_snapshot('[{"orderNo":1,"keyword":"open"}]')
    subject = (
        UiCaseRunSnapshot(task_id="task-1", run_id="run-1", case=case)
        if normalize is normalize_case_steps
        else UiSuiteRunItemSnapshot(
            item_id="item-1",
            continue_on_failure=False,
            case=case,
        )
    )

    with pytest.raises(ValueError, match="case.steps_json 必须是数组"):
        normalize(subject)


@pytest.mark.parametrize("normalize", [normalize_case_steps, normalize_suite_steps])
def test_runner_prefers_explicit_steps_before_validating_legacy_steps_json(normalize) -> None:
    explicit_step = UiStepDefinition(keyword="click", order_no=1)
    case = case_snapshot('[{"orderNo":2,"keyword":"open"}]')
    case.steps = [explicit_step]
    subject = (
        UiCaseRunSnapshot(task_id="task-1", run_id="run-1", case=case)
        if normalize is normalize_case_steps
        else UiSuiteRunItemSnapshot(
            item_id="item-1",
            continue_on_failure=False,
            case=case,
        )
    )

    assert normalize(subject) == [explicit_step]


@pytest.mark.parametrize("normalize", [normalize_case_steps, normalize_suite_steps])
def test_runner_rejects_non_object_steps_json_items(normalize) -> None:
    case = case_snapshot(["open"])
    subject = (
        UiCaseRunSnapshot(task_id="task-1", run_id="run-1", case=case)
        if normalize is normalize_case_steps
        else UiSuiteRunItemSnapshot(
            item_id="item-1",
            continue_on_failure=False,
            case=case,
        )
    )

    with pytest.raises(ValueError, match="每个步骤必须是对象"):
        normalize(subject)
