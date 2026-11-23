"""Validate binding and persistent slots before connecting the live workflow."""

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.repositories.deletion import delete_owned_data
from testing_agent.repositories.generation_candidate_creation import (
    CandidateCreationConflict,
    CandidateProvenance,
    create_candidate_from_successful_attempt,
)
from testing_agent.repositories.generation_candidate_storage import (
    CandidateEditSnapshot,
    edit_unfrozen_candidate_if_unchanged,
)
from testing_agent.repositories.generation_current_chain import (
    ChainBindingConflict,
    bind_current_chain,
    ensure_empty_slot,
)


async def test_chain_binding_is_scoped_and_slot_is_stable(database):  # noqa: F811
    sync, _, _ = database
    sync.add_all(
        [
            AiGenerateTask(
                task_id="other-task",
                task_type="functional_case_generate",
                name="other",
                project_id="p",
                sprint_id="s",
                requirement_id="other",
                creator_user_id="u",
                source_type="text",
                source_content="",
            ),
            AiGenerateTask(
                task_id="second-task",
                task_type="functional_case_generate",
                name="second",
                project_id="p",
                sprint_id="s",
                requirement_id="req",
                creator_user_id="u",
                source_type="text",
                source_content="",
            ),
        ]
    )
    sync.flush()
    sync.add_all(
        [
            AiGenerationStage(id="valid-stage", task_id="task", stage="case_names"),
            AiGenerationStage(id="wrong-kind-stage", task_id="task", stage="ui_yaml"),
            AiGenerationStage(id="foreign-stage", task_id="other-task", stage="case_names"),
        ]
    )
    sync.commit()
    session = AsyncSessionAdapter(sync)

    with pytest.raises(ChainBindingConflict):
        await bind_current_chain(
            session, requirement_id="req", kind="function", task_id="other-task"
        )
    with pytest.raises(ChainBindingConflict):
        await bind_current_chain(session, requirement_id="req", kind="ui", task_id="task")
    chain = await bind_current_chain(session, requirement_id="req", kind="function", task_id="task")
    same = await bind_current_chain(session, requirement_id="req", kind="function", task_id="task")
    assert same.chain_id == chain.chain_id
    with pytest.raises(ChainBindingConflict):
        await bind_current_chain(
            session, requirement_id="req", kind="function", task_id="second-task"
        )
    with pytest.raises(ChainBindingConflict):
        await ensure_empty_slot(session, chain_id=chain.chain_id, stage_id="foreign-stage")
    with pytest.raises(ChainBindingConflict):
        await ensure_empty_slot(session, chain_id=chain.chain_id, stage_id="wrong-kind-stage")
    slot = await ensure_empty_slot(session, chain_id=chain.chain_id, stage_id="valid-stage")
    token = slot.content_token
    assert token and slot.content is None
    same_slot = await ensure_empty_slot(session, chain_id=chain.chain_id, stage_id="valid-stage")
    assert same_slot.content_token == token
    await session.rollback()
    assert await bind_current_chain(session, requirement_id="req", kind="function", task_id="task")


async def test_successful_attempt_creates_one_candidate_and_replay_does_not_restore_old_content(
    database,  # noqa: F811
):
    sync, _, _ = database
    sync.add(AiGenerationStage(id="creation-stage", task_id="task", stage="case_names"))
    sync.flush()
    sync.add_all(
        [
            AiGenerationAttempt(
                id="success-attempt",
                stage_id="creation-stage",
                attempt_no=1,
                operation="generate",
                requested_by="u",
                input_snapshot_json={"source": {"document": "original"}},
                status="success",
                output_content='{"a": 1}',
                output_format="json",
                invalidated_reason="",
            ),
            AiGenerationAttempt(
                id="failed-attempt",
                stage_id="creation-stage",
                attempt_no=2,
                operation="generate",
                requested_by="u",
                status="failed",
                invalidated_reason="",
            ),
        ]
    )
    sync.commit()
    session = AsyncSessionAdapter(sync)
    chain = await bind_current_chain(session, requirement_id="req", kind="function", task_id="task")
    provenance = CandidateProvenance("trial", {"sources": []}, "lineage", "basis")
    with pytest.raises(CandidateCreationConflict):
        await create_candidate_from_successful_attempt(
            session,
            chain_id=chain.chain_id,
            stage_id="creation-stage",
            attempt_id="failed-attempt",
            provenance=provenance,
        )
    assert sync.query(AiGenerationStageContent).count() == 0
    candidate = await create_candidate_from_successful_attempt(
        session,
        chain_id=chain.chain_id,
        stage_id="creation-stage",
        attempt_id="success-attempt",
        provenance=provenance,
    )
    original_id, token = candidate.candidate_id, candidate.candidate_token
    assert candidate.content == '{"a": 1}' and candidate.generation_mode == "trial"
    assert candidate.source_snapshot_json == {"source": {"document": "original"}}
    edited = await edit_unfrozen_candidate_if_unchanged(
        session,
        chain_id=chain.chain_id,
        stage_id="creation-stage",
        candidate_id=original_id,
        expected_candidate_token=token,
        expected_attempt_id="success-attempt",
        replacement=CandidateEditSnapshot(
            "edited-attempt", '{"a": 2}', "json", None, "edited-hash"
        ),
    )
    assert edited
    replay = await create_candidate_from_successful_attempt(
        session,
        chain_id=chain.chain_id,
        stage_id="creation-stage",
        attempt_id="success-attempt",
        provenance=provenance,
    )
    assert replay.candidate_id == original_id and replay.content == '{"a": 2}'
    with pytest.raises(CandidateCreationConflict):
        await create_candidate_from_successful_attempt(
            session,
            chain_id=chain.chain_id,
            stage_id="creation-stage",
            attempt_id="success-attempt",
            provenance=CandidateProvenance("trial", {"sources": []}, "different", "basis"),
        )
    sync.add(
        AiGenerationAttempt(
            id="child-attempt",
            stage_id="creation-stage",
            attempt_no=3,
            operation="revise",
            requested_by="u",
            status="success",
            output_content='{"a": 3}',
            output_format="json",
            invalidated_reason="",
        )
    )
    sync.flush()
    child = await create_candidate_from_successful_attempt(
        session,
        chain_id=chain.chain_id,
        stage_id="creation-stage",
        attempt_id="child-attempt",
        provenance=CandidateProvenance("trial", {"sources": []}, "lineage", "basis", original_id),
    )
    assert child.derived_from_candidate_id == original_id and replay.frozen_at is not None
    assert (
        await edit_unfrozen_candidate_if_unchanged(
            session,
            chain_id=chain.chain_id,
            stage_id="creation-stage",
            candidate_id=original_id,
            expected_candidate_token=edited[0],
            expected_attempt_id="edited-attempt",
            replacement=CandidateEditSnapshot("another-edit", '{"a": 4}', "json", None, "hash"),
        )
        is None
    )


async def test_task_cleanup_handles_current_and_derived_candidates_without_deleting_assets(
    database,  # noqa: F811
):
    sync, _, _ = database
    sync.add(AiGenerationStage(id="delete-stage", task_id="task", stage="case_names"))
    sync.add(FunctionTestSuite(suite_id="retained-suite", requirement_id="req", name="retained"))
    sync.commit()
    session = AsyncSessionAdapter(sync)
    chain = await bind_current_chain(session, requirement_id="req", kind="function", task_id="task")
    sync.add(
        AiGenerationCandidate(
            candidate_id="parent",
            snapshot_id="parent-snapshot",
            chain_id=chain.chain_id,
            stage_id="delete-stage",
            content="parent",
            format="text",
            candidate_token="parent-token",
            disposition="available",
            generation_mode="current",
            created_by="u",
        )
    )
    sync.flush()
    sync.add(
        AiGenerationCandidate(
            candidate_id="child",
            snapshot_id="child-snapshot",
            chain_id=chain.chain_id,
            stage_id="delete-stage",
            content="child",
            format="text",
            candidate_token="child-token",
            disposition="available",
            generation_mode="trial",
            created_by="u",
            derived_from_candidate_id="parent",
        )
    )
    sync.flush()
    sync.add(
        AiGenerationStageContent(
            stage_id="delete-stage",
            chain_id=chain.chain_id,
            stage="case_names",
            content="parent",
            content_token="slot-token",
            source_candidate_id="parent",
        )
    )
    sync.commit()
    task = sync.query(AiGenerateTask).filter_by(task_id="task").one()
    await delete_owned_data(session, task)
    assert sync.query(RequirementGenerationChain).count() == 0
    assert sync.query(AiGenerationCandidate).count() == 0
    assert sync.query(AiGenerationStageContent).count() == 0
    assert sync.query(FunctionTestSuite).filter_by(suite_id="retained-suite").one()
