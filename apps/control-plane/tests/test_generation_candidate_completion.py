"""Only successful candidate-protocol attempts append an immutable candidate."""

from copy import deepcopy
from uuid import uuid4

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_candidate_graph import SOURCE_SNAPSHOT
from support.generation_source_seed import seed_graph

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.schemas.generation_candidates import CandidateRevisionRequest
from testing_agent.services.generation_candidate_completion import publish_candidate_attempt
from testing_agent.services.generation_revision_snapshot import build_revision_snapshot
from testing_agent.services.stage_storage import DirectStageStorage
from testing_agent.services.stage_storage.worker import StageWorkerTransitions


def snapshot(graph):
    return {
        **deepcopy(SOURCE_SNAPSHOT),
        "candidateProtocol": "single-current/1",
        "candidateInput": deepcopy(graph["p"].source_manifest),
        "candidateBasisHash": graph["p"].basis_hash,
    }


async def test_worker_completion_appends_and_replays_same_candidate(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    session = AsyncSessionAdapter(sync)
    attempt = await DirectStageStorage(session).prepare(
        "stage-p",
        worker_task_id="worker",
        requested_by="u",
        input_snapshot=snapshot(graph),
        allow_multiple_candidates=True,
    )
    result = await StageWorkerTransitions(session).completed(
        "stage-p",
        attempt.id,
        "worker",
        content="new test points",
        output_format="text",
        output_context={"summary": "ok"},
    )
    rows = sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=attempt.id).all()
    assert len(rows) == 1 and rows[0].content == "new test points"
    assert rows[0].candidate_id != "p" and rows[0].lineage_hash == graph["p"].lineage_hash
    stage = sync.query(AiGenerationStage).filter_by(id="stage-p").one()
    await publish_candidate_attempt(session, stage=stage, attempt=result)
    assert sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=attempt.id).count() == 1
    assert (
        sync.query(AiGenerationCandidate).filter_by(candidate_id="p").one().content == "content-p"
    )
    with pytest.raises(AppError, match="候选派生"):
        await DirectStageStorage(session).prepare(
            "stage-p",
            worker_task_id="revision",
            requested_by="u",
            input_snapshot={},
            operation="revise",
            expected_attempt_id=attempt.id,
            revision_instruction="change",
        )


async def test_invalid_basis_rolls_back_both_output_and_candidate(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    session = AsyncSessionAdapter(sync)
    inputs = snapshot(graph)
    inputs["candidateBasisHash"] = "tampered"
    attempt = await DirectStageStorage(session).prepare(
        "stage-p",
        worker_task_id="worker",
        requested_by="u",
        input_snapshot=inputs,
        allow_multiple_candidates=True,
    )
    sync.commit()
    with pytest.raises(AppError):
        await StageWorkerTransitions(session).completed(
            "stage-p",
            attempt.id,
            "worker",
            content="output",
            output_format="text",
            output_context=None,
        )
    # A caller that catches the failure still cannot commit a partial publish.
    sync.commit()
    assert sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=attempt.id).count() == 0
    assert (
        sync.query(AiGenerationStage).filter_by(id="stage-p").one().active_attempt_id == attempt.id
    )


async def test_revision_completion_creates_new_candidate_without_changing_parent(database):  # noqa: F811
    sync, _, _ = database
    seed_graph(sync)
    session = AsyncSessionAdapter(sync)
    parent = sync.query(AiGenerationCandidate).filter_by(candidate_id="p").one()
    parent.current_attempt_id = "attempt-p"
    request = CandidateRevisionRequest(
        expected_candidate_token=parent.candidate_token,
        expected_attempt_id="attempt-p",
        connection_id="llm",
        instruction="补充边界",
        request_id=uuid4(),
    )
    inputs = build_revision_snapshot(
        candidate=parent,
        kind="function",
        stage="case_names",
        request=request,
        signature="signature",
        attempt_id="revision-attempt",
        actor_id="u",
        attachments=(),
        attachment_hashes={},
    )
    attempt = await DirectStageStorage(session).prepare(
        "stage-p",
        worker_task_id="revision-worker",
        requested_by="u",
        input_snapshot=inputs,
        operation="revise",
        expected_attempt_id="attempt-p",
        revision_instruction=request.instruction,
        attempt_id="revision-attempt",
        allow_multiple_candidates=True,
    )
    result = await StageWorkerTransitions(session).completed(
        "stage-p",
        attempt.id,
        "revision-worker",
        content="revised test points",
        output_format="text",
        output_context=None,
    )
    derived = sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=attempt.id).one()
    assert derived.derived_from_candidate_id == "p"
    assert derived.content == "revised test points" and parent.content == "content-p"
    assert derived.source_manifest_json == inputs["candidateInput"]
    stage = sync.query(AiGenerationStage).filter_by(id="stage-p").one()
    await publish_candidate_attempt(session, stage=stage, attempt=result)
    assert sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=attempt.id).count() == 1


async def test_legacy_attempt_does_not_create_a_candidate(database):  # noqa: F811
    sync, _, _ = database
    seed_graph(sync)
    session = AsyncSessionAdapter(sync)
    attempt = await DirectStageStorage(session).prepare(
        "stage-p",
        worker_task_id="worker",
        requested_by="u",
        input_snapshot={},
    )
    await StageWorkerTransitions(session).completed(
        "stage-p",
        attempt.id,
        "worker",
        content="legacy output",
        output_format="text",
        output_context=None,
    )
    assert sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=attempt.id).count() == 0


def test_worker_snapshot_exposes_candidate_manifest_outside_model_inputs():
    from types import SimpleNamespace

    from support.generation_candidate_graph import fixture_graph

    from testing_agent.schemas.workers import WorkerSnapshotResponse
    from testing_agent.services.stage_storage.payload import worker_payloads

    inputs = snapshot(fixture_graph())
    inputs["llmConnectionId"] = "llm"
    authority = SimpleNamespace(
        input_snapshot=inputs,
        attempt_id="attempt",
        revision_instruction=None,
        task=SimpleNamespace(
            task_id="task",
            task_type="functional_case_generate",
            name="name",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
        ),
    )
    worker = SimpleNamespace(task_id="worker")
    claim, detailed = worker_payloads(authority, worker, stage_name="case_names", lease_seconds=30)
    assert "candidateInput" not in claim and "candidateInput" not in detailed["run"]
    assert detailed["candidateInput"]["lineageHash"] == inputs["candidateInput"]["lineageHash"]
    serialized = WorkerSnapshotResponse.model_validate(detailed).model_dump(
        mode="json", by_alias=True
    )
    assert serialized["candidateProtocol"] == "single-current/1"
    assert serialized["candidateInput"]["generationMode"] == "trial"
    inputs["candidateProtocol"] = "single-current/2"
    inputs["revisionParent"] = {"candidateId": "parent"}
    authority.revision_instruction = "补充边界"
    claim, detailed = worker_payloads(authority, worker, stage_name="case_names", lease_seconds=30)
    assert detailed["candidateProtocol"] == "single-current/1"
    assert "revisionParent" not in detailed
    assert "补充边界" in claim["configJson"]
    legacy = WorkerSnapshotResponse.model_validate({"run": {}}).model_dump(
        mode="json", by_alias=True
    )
    assert "candidateProtocol" not in legacy and "candidateInput" not in legacy
