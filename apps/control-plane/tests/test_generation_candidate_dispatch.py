"""Multiple candidate runs retain prior output and still serialize a stage."""

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_source_seed import seed_graph
from support.requirement_versions import candidate_selection

from testing_agent.core.errors import AppError
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.repositories.generation_candidate_creation import (
    CandidateProvenance,
    create_candidate_from_successful_attempt,
)
from testing_agent.services.stage_storage import DirectStageStorage


async def test_candidate_dispatch_allows_new_attempt_but_not_parallel_attempts(database):  # noqa: F811
    sync, _, statements = database
    seed_graph(sync)
    session = AsyncSessionAdapter(sync)
    storage = DirectStageStorage(session)
    first = await storage.prepare(
        "stage-p", worker_task_id="worker-one", requested_by="u", input_snapshot={}
    )
    await storage.publish(
        "stage-p",
        attempt_id=first.id,
        worker_task_id="worker-one",
        content="result one",
        output_format="text",
        output_context=None,
    )
    candidate = await create_candidate_from_successful_attempt(
        session,
        chain_id="function-chain",
        stage_id="stage-p",
        attempt_id=first.id,
        provenance=CandidateProvenance("trial", None, None, None),
    )
    sync.commit()
    with pytest.raises(AppError, match="待审核"):
        await storage.prepare(
            "stage-p", worker_task_id="legacy", requested_by="u", input_snapshot={}
        )
    sync.rollback()
    statements.clear()
    second = await storage.prepare(
        "stage-p",
        worker_task_id="worker-two",
        requested_by="u",
        input_snapshot={},
        allow_multiple_candidates=True,
    )
    assert second.id != first.id
    assert not any("ai_generate_stage_versions" in statement.lower() for statement in statements)
    assert (
        sync.query(AiGenerationCandidate)
        .filter_by(candidate_id=candidate.candidate_id)
        .one()
        .content
        == "result one"
    )
    with pytest.raises(AppError, match="正在运行"):
        await storage.prepare(
            "stage-p",
            worker_task_id="worker-three",
            requested_by="u",
            input_snapshot={},
            allow_multiple_candidates=True,
        )
    sync.rollback()


async def test_verified_dispatch_replays_and_next_success_appends_candidate(database):  # noqa: F811
    from uuid import uuid4

    from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.generation_candidates import CandidateRunRequest
    from testing_agent.services.generation_candidate_dispatch import dispatch_candidate_stage
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions

    sync, _, _ = database
    seed_graph(sync)
    session = AsyncSessionAdapter(sync)
    task = sync.query(AiGenerateTask).filter_by(task_id="material-task").one()
    source = {
        "requirementId": "req",
        "documentFileId": "file",
        "documentHash": "hash",
        "documentType": "docx",
        "documentFilename": "requirement.docx",
        "documentDownloadUrl": "/internal/ai-worker/tasks/id/requirement-document",
        "sourceContent": "/internal/ai-worker/tasks/id/requirement-document",
        "workflowVersion": 2,
    }
    root = fingerprint_root_input("requirement_document", source)
    request = CandidateRunRequest(connection_id="llm", request_id=uuid4(), instruction="first")
    options = dict(
        task=task,
        kind="requirement_analysis",
        stage="extracting_text",
        actor_id="u",
        request=request,
        source=source,
        direct_roots=(root,),
        current_root_hashes={root.key: root.content_hash},
    )
    first = await dispatch_candidate_stage(session, **options)
    assert (
        not first.replayed
        and first.attempt.input_snapshot_json["candidateProtocol"] == "single-current/1"
    )
    sync.commit()
    replay = await dispatch_candidate_stage(
        session, **{**options, "source": {}, "direct_roots": (), "current_root_hashes": {}}
    )
    assert replay.replayed and replay.attempt.id == first.attempt.id
    assert sync.query(WorkerTask).filter_by(task_id=str(request.request_id)).count() == 1
    sync.commit()
    changed = request.model_copy(update={"instruction": "different"})
    with pytest.raises(AppError, match="请求标识"):
        await dispatch_candidate_stage(session, **{**options, "request": changed})
    sync.rollback()
    assert sync.query(AiGenerationAttempt).filter_by(stage_id="stage-m").count() == 1
    await StageWorkerTransitions(session).completed(
        "stage-m",
        first.attempt.id,
        str(request.request_id),
        content="material candidate",
        output_format="text",
        output_context=None,
    )
    sync.commit()
    assert (
        sync.query(AiGenerationCandidate)
        .filter_by(origin_attempt_id=first.attempt.id)
        .one()
        .content
        == "material candidate"
    )
    second_request = request.model_copy(update={"request_id": uuid4()})
    second = await dispatch_candidate_stage(session, **{**options, "request": second_request})
    assert second.attempt.id != first.attempt.id and not second.replayed
    assert (
        sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=first.attempt.id).count() == 1
    )


async def test_review_and_material_dispatch_independently(database):  # noqa: F811
    from uuid import uuid4

    from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_stage import AiGenerationStage
    from testing_agent.schemas.generation_candidates import CandidateRunRequest
    from testing_agent.services.generation_candidate_dispatch import dispatch_candidate_stage

    sync, _, _ = database
    seed_graph(sync)
    sync.add(
        AiGenerationStage(id="stage-review", task_id="material-task", stage="requirement_review")
    )
    sync.commit()
    session = AsyncSessionAdapter(sync)
    task = sync.query(AiGenerateTask).filter_by(task_id="material-task").one()
    source = {
        "requirementId": "req",
        "documentFileId": "file",
        "documentHash": "hash",
        "documentType": "docx",
        "documentFilename": "requirement.docx",
        "documentDownloadUrl": "/internal/ai-worker/tasks/id/requirement-document",
        "sourceContent": "/internal/ai-worker/tasks/id/requirement-document",
        "workflowVersion": 2,
    }
    root = fingerprint_root_input("requirement_document", source)
    attempts = []
    for stage in ("requirement_review", "extracting_text"):
        result = await dispatch_candidate_stage(
            session,
            task=task,
            kind="requirement_analysis",
            stage=stage,
            actor_id="u",
            request=CandidateRunRequest(connection_id="llm", request_id=uuid4()),
            source=source,
            direct_roots=(root,),
            current_root_hashes={root.key: root.content_hash},
        )
        sync.commit()
        attempts.append(result.attempt.id)
    assert attempts[0] != attempts[1]


async def test_candidate_chain_can_trial_each_stage_without_adopting(database):  # noqa: F811
    import json
    from uuid import uuid4

    from support.requirement_versions import material_artifact, points_artifact, scope_artifact

    from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
    from testing_agent.domain.generation_source_closure import SourceClosureError
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_stage import AiGenerationStage
    from testing_agent.models.generation_candidates import AiGenerationStageContent
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.generation_candidates import CandidateRunRequest
    from testing_agent.services.generation_candidate_dispatch import dispatch_candidate_stage
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions

    sync, _, _ = database
    seed_graph(sync)
    sync.add(AiGenerationStage(id="stage-d", task_id="task", stage="detailed_cases"))
    sync.commit()
    session = AsyncSessionAdapter(sync)
    material_task = sync.query(AiGenerateTask).filter_by(task_id="material-task").one()
    function_task = sync.query(AiGenerateTask).filter_by(task_id="task").one()
    document_source = {
        "requirementId": "req",
        "documentFileId": "file",
        "documentHash": "hash",
        "documentType": "docx",
        "documentFilename": "requirement.docx",
        "documentDownloadUrl": "/internal/ai-worker/tasks/id/requirement-document",
        "sourceContent": "/internal/ai-worker/tasks/id/requirement-document",
        "workflowVersion": 2,
    }
    root = fingerprint_root_input("requirement_document", document_source)
    common = {
        "actor_id": "u",
        "direct_roots": (root,),
        "current_root_hashes": {root.key: root.content_hash},
    }
    function_source = {"taskId": "task", "requirementId": "req", "sourceType": "text"}

    async def dispatch(task, kind, stage, source, selections=()):
        request = CandidateRunRequest(
            connection_id="llm",
            request_id=uuid4(),
            generation_mode="trial" if selections else "current",
            source_selections=list(selections),
        )
        result = await dispatch_candidate_stage(
            session,
            task=task,
            kind=kind,
            stage=stage,
            request=request,
            source=source,
            **common,
        )
        sync.commit()
        return result, request

    async def finish(result, request, stage_id, value):
        await StageWorkerTransitions(session).completed(
            stage_id,
            result.attempt.id,
            str(request.request_id),
            content=json.dumps(value),
            output_format="json",
            output_context=None,
        )
        sync.commit()
        return (
            sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=result.attempt.id).one()
        )

    material_run, material_request = await dispatch(
        material_task, "requirement_analysis", "extracting_text", document_source
    )
    material = await finish(material_run, material_request, "stage-m", material_artifact())
    analysis_run, analysis_request = await dispatch(
        function_task,
        "function",
        "requirement_analysis",
        function_source,
        (candidate_selection(material, "requirement_analysis", "extracting_text"),),
    )
    assert (
        json.loads(analysis_run.attempt.input_snapshot_json["source"]["sourceContent"])
        == material_artifact()
    )
    analysis = await finish(analysis_run, analysis_request, "stage-a", scope_artifact())
    invalid = CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        generation_mode="trial",
        source_selections=[candidate_selection(analysis, "function", "requirement_analysis")],
    )
    with pytest.raises(SourceClosureError, match="source_conflict"):
        await dispatch_candidate_stage(
            session,
            task=function_task,
            kind="function",
            stage="case_names",
            request=invalid,
            source={**function_source, "requirementId": "other"},
            **common,
        )
    assert sync.query(WorkerTask).filter_by(task_id=str(invalid.request_id)).count() == 0
    sync.expire_all()
    assert (
        sync.query(AiGenerationCandidate)
        .filter_by(candidate_id=analysis.candidate_id)
        .one()
        .frozen_at
        is None
    )
    default = CandidateRunRequest(connection_id="llm", request_id=uuid4())
    with pytest.raises(SourceClosureError, match="pending_upstream"):
        await dispatch_candidate_stage(
            session,
            task=function_task,
            kind="function",
            stage="case_names",
            request=default,
            source=function_source,
            **common,
        )
    assert sync.query(WorkerTask).filter_by(task_id=str(default.request_id)).count() == 0
    sync.rollback()
    points_run, points_request = await dispatch(
        function_task,
        "function",
        "case_names",
        function_source,
        (candidate_selection(analysis, "function", "requirement_analysis"),),
    )
    assert (
        points_run.attempt.input_snapshot_json["config"]["requirementAnalysis"] == scope_artifact()
    )
    points = await finish(points_run, points_request, "stage-p", points_artifact())
    final, _ = await dispatch(
        function_task,
        "function",
        "detailed_cases",
        function_source,
        (
            candidate_selection(analysis, "function", "requirement_analysis"),
            candidate_selection(points, "function", "case_names"),
        ),
    )
    config = final.attempt.input_snapshot_json["config"]
    assert (
        config["requirementAnalysis"] == scope_artifact()
        and config["caseNames"] == points_artifact()
    )
    assert all(
        slot.source_candidate_id is None for slot in sync.query(AiGenerationStageContent).all()
    )
