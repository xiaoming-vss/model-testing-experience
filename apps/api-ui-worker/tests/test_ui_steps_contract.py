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


def snapshot_for(normalize, steps_json: object):
    case = case_snapshot(steps_json)
    return (
        UiCaseRunSnapshot(task_id="task-1", run_id="run-1", case=case)
        if normalize is normalize_case_steps
        else UiSuiteRunItemSnapshot(
            item_id="item-1",
            continue_on_failure=False,
            case=case,
        )
    )


@pytest.mark.parametrize("normalize", [normalize_case_steps, normalize_suite_steps])
def test_runner_uses_steps_json_array(normalize) -> None:
    steps = normalize(snapshot_for(normalize, [{"orderNo": 1, "keyword": "open"}]))

    assert [(step.order_no, step.keyword) for step in steps] == [(1, "open")]


@pytest.mark.parametrize("normalize", [normalize_case_steps, normalize_suite_steps])
def test_runner_rejects_steps_json_string(normalize) -> None:
    subject = snapshot_for(normalize, '[{"orderNo":1,"keyword":"open"}]')

    with pytest.raises(ValueError, match="case.steps_json 必须是数组"):
        normalize(subject)


@pytest.mark.parametrize("normalize", [normalize_case_steps, normalize_suite_steps])
def test_runner_prefers_explicit_steps_before_validating_legacy_steps_json(
    normalize,
) -> None:
    explicit_step = UiStepDefinition(keyword="click", order_no=1)
    subject = snapshot_for(normalize, '[{"orderNo":2,"keyword":"open"}]')
    subject.case.steps = [explicit_step]

    assert normalize(subject) == [explicit_step]


@pytest.mark.parametrize("normalize", [normalize_case_steps, normalize_suite_steps])
def test_runner_rejects_non_object_steps_json_items(normalize) -> None:
    subject = snapshot_for(normalize, ["open"])

    with pytest.raises(ValueError, match="每个步骤必须是对象"):
        normalize(subject)
