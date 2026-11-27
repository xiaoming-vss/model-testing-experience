"""A whole candidate branch can be generated and adopted on real MySQL."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from support.mysql_initialization import async_sessions, mysql, seed_row  # noqa: F401
from support.requirement_versions import material_artifact, points_artifact, scope_artifact

from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models import Base
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
    AiGenerationStageContent,
)
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.generation_candidates import (
    CandidateAdoptRequest,
    CandidateRunRequest,
    CurrentClearRequest,
    SourceSelection,
)
from testing_agent.services.generation_candidate_adoption import adopt_verified_candidate
from testing_agent.services.generation_candidate_adoption_receipt import adopt_candidate_once
from testing_agent.services.generation_candidate_dispatch import dispatch_candidate_stage
from testing_agent.services.generation_current_clear import clear_current_once
from testing_agent.services.stage_storage.worker import StageWorkerTransitions


def test_generate_trial_branch_and_adopt_independently(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        seed_row(
            connection,
            tables["requirements"],
            {"requirement_id": "req", "sprint_id": sprint["sprint_id"]},
        )
        scope = {
            "project_id": project["project_id"],
            "sprint_id": sprint["sprint_id"],
            "requirement_id": "req",
        }
        tasks = {
            "requirement_analysis": seed_row(
                connection,
                tables["ai_generate_tasks"],
                {**scope, "task_type": "requirement_analysis"},
            ),
            "function": seed_row(
                connection,
                tables["ai_generate_tasks"],
                {**scope, "task_type": "functional_case_generate"},
            ),
        }
        for kind, task in tasks.items():
            seed_row(
                connection,
                tables["requirement_generation_chains"],
                {
                    "task_id": task["task_id"],
                    "requirement_id": "req",
                    "kind": kind,
                },
            )
        stages = {}
        for kind, names in (
            ("requirement_analysis", ("extracting_text",)),
            ("function", ("requirement_analysis", "case_names", "detailed_cases")),
        ):
            for name in names:
                stage = seed_row(
                    connection,
                    tables["ai_generation_stages"],
                    {
                        "task_id": tasks[kind]["task_id"],
                        "stage": name,
                    },
                )
                stages[name] = stage["id"]
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
    function_source = {
        "taskId": tasks["function"]["task_id"],
        "requirementId": "req",
        "sourceType": "text",
    }

    async def exercise():
        engine, factory = async_sessions(mysql)
        try:

            async def generate(kind, stage, source, selections, output, output_format="json"):
                request = CandidateRunRequest(
                    connection_id="llm",
                    request_id=uuid4(),
                    generation_mode="trial" if selections else "current",
                    source_selections=list(selections),
                )
                async with factory() as session:
                    task = await session.scalar(
                        sa.select(AiGenerateTask).where(
                            AiGenerateTask.task_id == tasks[kind]["task_id"]
                        )
                    )
                    assert task is not None
                    result = await dispatch_candidate_stage(
                        session,
                        task=task,
                        kind=kind,
                        stage=stage,
                        actor_id="u",
                        request=request,
                        source=source,
                        direct_roots=(root,),
                        current_root_hashes={root.key: root.content_hash},
                    )
                    attempt_id = result.attempt.id
                    await session.commit()
                async with factory() as session:
                    await StageWorkerTransitions(session).completed(
                        stages[stage],
                        attempt_id,
                        str(request.request_id),
                        content=json.dumps(output) if output_format == "json" else output,
                        output_format=output_format,
                        output_context=None,
                    )
                    await session.commit()
                    candidate = await session.scalar(
                        sa.select(AiGenerationCandidate).where(
                            AiGenerationCandidate.origin_attempt_id == attempt_id
                        )
                    )
                    assert candidate is not None
                    return candidate

            def choose(candidate, kind, stage):
                return SourceSelection(
                    chain_kind=kind,
                    stage=stage,
                    source_kind="candidate",
                    candidate_id=candidate.candidate_id,
                    snapshot_id=candidate.snapshot_id,
                    expected_candidate_token=candidate.candidate_token,
                )

            material = await generate(
                "requirement_analysis", "extracting_text", document_source, (), material_artifact()
            )
            analysis = await generate(
                "function",
                "requirement_analysis",
                function_source,
                (choose(material, "requirement_analysis", "extracting_text"),),
                scope_artifact(),
            )
            points = await generate(
                "function",
                "case_names",
                function_source,
                (choose(analysis, "function", "requirement_analysis"),),
                points_artifact(),
            )
            final = await generate(
                "function",
                "detailed_cases",
                function_source,
                (
                    choose(analysis, "function", "requirement_analysis"),
                    choose(points, "function", "case_names"),
                ),
                "case output",
                "text",
            )
            async with factory() as session:
                slots = (await session.scalars(sa.select(AiGenerationStageContent))).all()
                assert len(slots) == 4 and all(slot.source_candidate_id is None for slot in slots)

            async def adopt(candidate, kind, stage):
                async with factory() as session:
                    slot = await session.scalar(
                        sa.select(AiGenerationStageContent).where(
                            AiGenerationStageContent.stage_id == stages[stage]
                        )
                    )
                    assert slot is not None
                    request = CandidateAdoptRequest(
                        action="adopt",
                        candidate_id=candidate.candidate_id,
                        expected_candidate_token=candidate.candidate_token,
                        expected_attempt_id=candidate.current_attempt_id,
                        expected_current_token=slot.content_token,
                        request_id=uuid4(),
                    )
                    try:
                        await adopt_verified_candidate(
                            session,
                            requirement_id="req",
                            kind=kind,
                            stage=stage,
                            request=request,
                            actor_id="u",
                            current_root_hashes={root.key: root.content_hash},
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        raise

            await adopt(final, "function", "detailed_cases")
            async with factory() as session:
                final_slot = await session.scalar(
                    sa.select(AiGenerationStageContent).where(
                        AiGenerationStageContent.stage_id == stages["detailed_cases"]
                    )
                )
                assert final_slot is not None
                assert final_slot.source_candidate_id == final.candidate_id
            await adopt(material, "requirement_analysis", "extracting_text")
            await adopt(analysis, "function", "requirement_analysis")
            await adopt(points, "function", "case_names")
            async with factory() as session:
                point_slot = await session.scalar(
                    sa.select(AiGenerationStageContent).where(
                        AiGenerationStageContent.stage_id == stages["case_names"]
                    )
                )
                assert point_slot is not None
                original_point_token = point_slot.content_token
            guarded = CandidateRunRequest(
                connection_id="llm",
                request_id=uuid4(),
                required_current_source=SourceSelection(
                    chain_kind="function",
                    stage="case_names",
                    source_kind="current",
                    expected_current_token=original_point_token,
                ),
            )
            # Emulate an adoption followed by a competing replacement before
            # continuation acquires its source locks. No worker may survive.
            async with factory() as writer:
                await writer.execute(
                    sa.update(AiGenerationStageContent)
                    .where(AiGenerationStageContent.stage_id == stages["case_names"])
                    .values(content_token="replaced-before-continuation")
                )
                await writer.commit()
            async with factory() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask).where(
                        AiGenerateTask.task_id == tasks["function"]["task_id"]
                    )
                )
                assert task is not None
                with pytest.raises(SourceClosureError, match="concurrent_change"):
                    await dispatch_candidate_stage(
                        session,
                        task=task,
                        kind="function",
                        stage="detailed_cases",
                        actor_id="u",
                        request=guarded,
                        source=function_source,
                        direct_roots=(root,),
                        current_root_hashes={root.key: root.content_hash},
                    )
                await session.rollback()
                assert (
                    await session.scalar(
                        sa.select(WorkerTask.task_id).where(
                            WorkerTask.task_id == str(guarded.request_id)
                        )
                    )
                    is None
                )
            async with factory() as writer:
                await writer.execute(
                    sa.update(AiGenerationStageContent)
                    .where(AiGenerationStageContent.stage_id == stages["case_names"])
                    .values(content_token=original_point_token)
                )
                await writer.commit()
            async with factory() as session:
                slots = (await session.scalars(sa.select(AiGenerationStageContent))).all()
                assert {slot.source_candidate_id for slot in slots} == {
                    material.candidate_id,
                    analysis.candidate_id,
                    points.candidate_id,
                    final.candidate_id,
                }
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerationCandidate)
                    )
                    == 4
                )

            async with factory() as session:
                slot = await session.scalar(
                    sa.select(AiGenerationStageContent).where(
                        AiGenerationStageContent.stage_id == stages["detailed_cases"]
                    )
                )
                assert slot is not None
                replay_request = CandidateAdoptRequest(
                    action="adopt",
                    candidate_id=final.candidate_id,
                    expected_candidate_token=final.candidate_token,
                    expected_attempt_id=final.current_attempt_id,
                    expected_current_token=slot.content_token,
                    request_id=uuid4(),
                )

            async def retry_same_adoption():
                async with factory() as session:
                    result = await adopt_candidate_once(
                        session,
                        requirement_id="req",
                        kind="function",
                        stage="detailed_cases",
                        request=replay_request,
                        actor_id="u",
                        current_root_hashes={root.key: root.content_hash},
                    )
                    await session.commit()
                    return result

            responses = await asyncio.gather(retry_same_adoption(), retry_same_adoption())
            assert sorted(result.replayed for result in responses) == [False, True]
            assert len({result.content_token for result in responses}) == 1
            async with factory() as session:
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerationReviewReceipt)
                    )
                    == 1
                )

            clear_request = CurrentClearRequest(
                expected_current_token=responses[0].content_token, request_id=uuid4()
            )

            async def retry_same_clear():
                async with factory() as session:
                    result = await clear_current_once(
                        session,
                        requirement_id="req",
                        kind="function",
                        stage="detailed_cases",
                        request=clear_request,
                        actor_id="u",
                    )
                    await session.commit()
                    return result

            clears = await asyncio.gather(retry_same_clear(), retry_same_clear())
            assert sorted(result.replayed for result in clears) == [False, True]
            assert len({result.content_token for result in clears}) == 1
            async with factory() as session:
                slot = await session.scalar(
                    sa.select(AiGenerationStageContent).where(
                        AiGenerationStageContent.stage_id == stages["detailed_cases"]
                    )
                )
                assert slot is not None and slot.source_candidate_id is None
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerationCandidate)
                    )
                    == 4
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())
