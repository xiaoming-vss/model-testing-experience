"""Keep the review contract and its independent runtime copies in sync."""

import json
from pathlib import Path

import pytest

from testing_agent.domain.requirement_artifacts import validate_artifact

APP = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
FIXTURES = APP / "tests/fixtures/requirement_review"
CONTROL_PLANE_SCHEMA = (
    APP / "src/testing_agent/domain/requirement_schemas/requirement-review.schema.json"
)
WORKER_SCHEMA = (
    ROOT
    / "apps/ai-worker/src/testing_agent_ai_worker"
    / "requirement_schemas/requirement-review.schema.json"
)
SKILL_SCHEMA = APP / "default-skills/mtx-review-requirement/references/output.schema.json"
CONTROL_PLANE_VALIDATOR = APP / "src/testing_agent/domain/requirement_artifacts.py"
WORKER_VALIDATOR = ROOT / "apps/ai-worker/src/testing_agent_ai_worker/requirement_artifacts.py"


def example(name):
    return json.loads((FIXTURES / f"{name}.example.json").read_text())


def test_review_examples_validate():
    for name in ("blocked", "needs-clarification", "passed"):
        assert validate_artifact(example(name), "requirement_review") == example(name)


def test_review_schema_copies_are_identical():
    if not WORKER_SCHEMA.exists() or not SKILL_SCHEMA.exists():
        pytest.skip("worker or skill schema is not available")
    control_plane = CONTROL_PLANE_SCHEMA.read_text(encoding="utf-8")
    assert control_plane == WORKER_SCHEMA.read_text(encoding="utf-8")
    assert control_plane == SKILL_SCHEMA.read_text(encoding="utf-8")


def test_review_validator_copies_are_identical():
    if not WORKER_VALIDATOR.exists():
        pytest.skip("worker validator is not available")
    assert CONTROL_PLANE_VALIDATOR.read_text(encoding="utf-8") == WORKER_VALIDATOR.read_text(
        encoding="utf-8"
    )


def test_review_status_must_match_issue_severity():
    review = example("blocked")
    review["reviewStatus"] = "passed"
    with pytest.raises(ValueError):
        validate_artifact(review, "requirement_review")
