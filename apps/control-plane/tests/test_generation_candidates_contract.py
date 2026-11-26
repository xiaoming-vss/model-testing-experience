"""Contract checks for the evolving requirement candidate workflow."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from testing_agent.domain.generation_chain import (
    HISTORICAL_REQUIREMENT_STAGE,
    HISTORICAL_TEST_STAGE,
    STAGE_DEFINITIONS,
    is_final_stage,
    upstream_stages,
)
from testing_agent.schemas.generation_candidates import (
    AdoptionBlock,
    AdoptionCheck,
    CandidateRunRequest,
    FrozenCandidateInput,
)

FIXTURE = Path(__file__).resolve().parents[3] / "tests/fixtures/generation-candidate-contract.json"


def test_run_contract_accepts_selected_sources_and_rejects_unsafe_requests() -> None:
    cases = json.loads(FIXTURE.read_text())
    for request in cases["validRuns"]:
        CandidateRunRequest.model_validate(request)
    for request in cases["invalidRuns"]:
        with pytest.raises(ValidationError):
            CandidateRunRequest.model_validate(request)


def test_adoption_block_reasons_are_distinct_and_consistent() -> None:
    cases = json.loads(FIXTURE.read_text())
    check = AdoptionCheck.model_validate(cases["blockedAdoption"])
    assert not check.can_adopt
    assert check.blocking_sources[0].stage == "case_names"
    assert check.blocking_sources[0].reason == "concurrent_change"
    block = AdoptionBlock(chain_kind="function", stage="case_names", reason="concurrent_change")
    assert block.reason == "concurrent_change"
    with pytest.raises(ValidationError):
        AdoptionCheck(can_adopt=True, lineage_hash="h", blocking_sources=check.blocking_sources)
    for reason in ("pending_upstream", "source_conflict", "source_stale", "source_unknown"):
        with pytest.raises(ValidationError):
            AdoptionBlock(chain_kind="function", stage="case_names", reason=reason)


def test_frozen_trial_contract_matches_worker_fixture() -> None:
    fixture = json.loads(FIXTURE.read_text())["frozenTrialInput"]
    assert FrozenCandidateInput.model_validate(fixture).model_dump(by_alias=True) == fixture


def test_frozen_selection_keeps_how_this_run_selected_the_same_snapshot() -> None:
    fixture = json.loads(FIXTURE.read_text())["frozenTrialInput"]
    fixture["generationMode"] = "current"
    fixture["selectedSources"][0]["sourceKind"] = "current"
    value = FrozenCandidateInput.model_validate(fixture)
    assert value.selected_sources[0].source_kind == "current"
    assert value.sources[0].source_kind == "candidate"
    fixture["selectedSources"][0]["snapshotId"] = "different-snapshot"
    with pytest.raises(ValidationError):
        FrozenCandidateInput.model_validate(fixture)


def test_requirement_review_remains_independent_and_all_stages_are_defined() -> None:
    assert sum(len(stages) for stages in STAGE_DEFINITIONS.values()) == 13
    assert upstream_stages("requirement_analysis", "extracting_text") == ()
    assert upstream_stages("requirement_analysis", HISTORICAL_REQUIREMENT_STAGE) == (
        "extracting_text",
    )
    assert is_final_stage("requirement_analysis", "extracting_text")
    assert is_final_stage("requirement_analysis", HISTORICAL_REQUIREMENT_STAGE)
    assert upstream_stages("requirement_analysis", HISTORICAL_TEST_STAGE) == (
        HISTORICAL_REQUIREMENT_STAGE,
    )
    assert is_final_stage("requirement_analysis", HISTORICAL_TEST_STAGE)
    assert upstream_stages("function", "detailed_cases") == ("requirement_analysis", "case_names")
    assert upstream_stages("api", "generate") == ("interface_extract", "api_design")
    assert upstream_stages("ui", "ui_yaml") == ("ui_surface", "ui_design")


def test_historical_verification_contract_copies_match_the_skill() -> None:
    apps = Path(__file__).resolve().parents[2]
    control = apps / "control-plane/src/testing_agent/domain"
    worker = apps / "ai-worker/src/testing_agent_ai_worker"
    skill = apps / "control-plane/default-skills/mtx-verify-historical-test-cases"
    for direction in ("input", "output"):
        file = f"requirement_schemas/historical-test-case-verification-{direction}.schema.json"
        assert (control / file).read_bytes() == (worker / file).read_bytes()
        assert (control / file).read_bytes() == (
            skill / f"references/{direction}.schema.json"
        ).read_bytes()
    contract = "historical_test_case_artifacts.py"
    assert (control / contract).read_bytes() == (worker / contract).read_bytes()
