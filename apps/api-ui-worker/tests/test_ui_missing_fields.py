from __future__ import annotations

import asyncio

import pytest

from test_worker.contracts.types import UiCaseSnapshot, UiStepDefinition
from test_worker.ui.step_executor import StepExecutionContext, StepExecutor
from test_worker.ui.step_normalizer import normalize_case_steps


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("explicit", [True, False])
def test_pending_raw_steps_never_disappear_during_normalization(enabled, explicit):
    case = UiCaseSnapshot(
        case_id="c",
        name="draft",
        steps_json=[
            {
                "keyword": "click",
                "enabled": enabled,
                "missingFields": [{"reason": "missing"}],
            }
        ],
        steps=[UiStepDefinition(keyword="click")] if explicit else None,
    )
    with pytest.raises(ValueError, match="missingFields"):
        normalize_case_steps(case)


def test_completed_steps_normalize_normally():
    case = UiCaseSnapshot(
        case_id="c",
        name="complete",
        steps_json=[
            {
                "keyword": "click",
                "locatorType": "css",
                "locatorValue": "#ok",
                "missingFields": [],
            }
        ],
    )
    assert normalize_case_steps(case)[0].locator_value == "#ok"


def test_explicit_pending_step_rejected_before_page_access():
    step = UiStepDefinition(keyword="click", missing_fields=[{"reason": "pending"}])
    case = UiCaseSnapshot(case_id="c", name="draft", steps=[step])
    with pytest.raises(ValueError, match="missingFields"):
        normalize_case_steps(case)
    context = StepExecutionContext(
        page=object(), artifact_dir="", default_step_timeout_ms=5000
    )
    with pytest.raises(ValueError, match="missingFields"):
        asyncio.run(StepExecutor().execute(step, 1, context))


@pytest.mark.parametrize("field", ["dataBindings", "sourceRefs"])
@pytest.mark.parametrize("enabled", [True, False])
def test_authoring_metadata_cannot_disappear_at_execution_boundary(field, enabled):
    case = UiCaseSnapshot(
        case_id="c",
        name="draft",
        steps_json=[{"keyword": "click", "enabled": enabled, field: {}}],
        steps=[UiStepDefinition(keyword="click")],
    )
    with pytest.raises(ValueError, match="补全草稿"):
        normalize_case_steps(case)


def test_legacy_descriptive_purpose_alone_is_not_a_completion_binding():
    case = UiCaseSnapshot(
        case_id="c",
        name="legacy",
        steps_json=[
            {
                "keyword": "click",
                "locatorType": "css",
                "locatorValue": "#ok",
                "purpose": "历史说明",
            }
        ],
    )
    assert normalize_case_steps(case)[0].locator_value == "#ok"
