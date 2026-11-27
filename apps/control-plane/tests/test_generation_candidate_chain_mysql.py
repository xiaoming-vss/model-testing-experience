"""A whole candidate branch can be generated and adopted on real MySQL."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from support.mysql_initialization import clean_schema as clean_schema
from support.mysql_initialization import mysql as mysql
from support.mysql_initialization import seed_row
from support.mysql_initialization import sessions as sessions
from support.requirement_versions import (
    candidate_selection,
    material_artifact,
    points_artifact,
    scope_artifact,
)

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

FINAL_STAGE = "detailed_cases"


@pytest.fixture
def chains(mysql):
    """Requirement ``req`` with empty requirement-analysis and function chains and stages."""
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
            ("function", ("requirement_analysis", "case_names", FINAL_STAGE)),
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
    return SimpleNamespace(
        tasks=tasks,
        stages=stages,
        document_source=document_source,
        root=fingerprint_root_input("requirement_document", document_source),
        function_source={
            "taskId": tasks["function"]["task_id"],
            "requirementId": "req",
            "sourceType": "text",
        },
    )


async def stage_slot(session, stage_id):
    """The current slot of a stage; it exists as soon as the stage does."""
    slot = await session.scalar(
        sa.select(AiGenerationStageContent).where(AiGenerationStageContent.stage_id == stage_id)
    )
    assert slot is not None
    return slot


async def generate(sessions, chains, kind, stage, source, selections, output, output_format="json"):
    """Run ``stage`` on a candidate of its own and complete it with ``output``."""
    request = CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        generation_mode="trial" if selections else "current",
        source_selections=list(selections),
    )
    async with sessions() as session:
        task = await session.scalar(
            sa.select(AiGenerateTask).where(AiGenerateTask.task_id == chains.tasks[kind]["task_id"])
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
            direct_roots=(chains.root,),
            current_root_hashes={chains.root.key: chains.root.content_hash},
        )
        attempt_id = result.attempt.id
        await session.commit()
    async with sessions() as session:
        await StageWorkerTransitions(session).completed(
            chains.stages[stage],
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


async def trial_branch(sessions, chains):
    """Generate material, analysis, points and cases as trials; returns the four candidates."""
    material = await generate(
        sessions,
        chains,
        "requirement_analysis",
        "extracting_text",
        chains.document_source,
        (),
        material_artifact(),
    )
    analysis = await generate(
        sessions,
        chains,
        "function",
        "requirement_analysis",
        chains.function_source,
        (candidate_selection(material, "requirement_analysis", "extracting_text"),),
        scope_artifact(),
    )
    points = await generate(
        sessions,
        chains,
        "function",
        "case_names",
        chains.function_source,
        (candidate_selection(analysis, "function", "requirement_analysis"),),
        points_artifact(),
    )
    final = await generate(
        sessions,
        chains,
        "function",
        FINAL_STAGE,
        chains.function_source,
        (
            candidate_selection(analysis, "function", "requirement_analysis"),
            candidate_selection(points, "function", "case_names"),
        ),
        "case output",
        "text",
    )
    return SimpleNamespace(material=material, analysis=analysis, points=points, final=final)


async def adopt(sessions, chains, candidate, kind, stage):
    """Adopt ``candidate`` into the current slot of ``stage``."""
    async with sessions() as session:
        slot = await stage_slot(session, chains.stages[stage])
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
                current_root_hashes={chains.root.key: chains.root.content_hash},
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def adopt_branch(sessions, chains, branch):
    """Adopt the cases first, then the three candidates they were generated from."""
    await adopt(sessions, chains, branch.final, "function", FINAL_STAGE)
    await adopt(sessions, chains, branch.material, "requirement_analysis", "extracting_text")
    await adopt(sessions, chains, branch.analysis, "function", "requirement_analysis")
    await adopt(sessions, chains, branch.points, "function", "case_names")


async def all_slots(sessions):
    """Every stage slot of the requirement; empty slots have no source candidate."""
    async with sessions() as session:
        return (await session.scalars(sa.select(AiGenerationStageContent))).all()


def slot_sources(slots):
    return {slot.source_candidate_id for slot in slots}


async def readopt_cases(sessions, chains, branch):
    """Ask twice at once to adopt the already adopted cases under one request."""
    final = branch.final
    async with sessions() as session:
        token = (await stage_slot(session, chains.stages[FINAL_STAGE])).content_token
    request = CandidateAdoptRequest(
        action="adopt",
        candidate_id=final.candidate_id,
        expected_candidate_token=final.candidate_token,
        expected_attempt_id=final.current_attempt_id,
        expected_current_token=token,
        request_id=uuid4(),
    )

    async def retry():
        async with sessions() as session:
            result = await adopt_candidate_once(
                session,
                requirement_id="req",
                kind="function",
                stage=FINAL_STAGE,
                request=request,
                actor_id="u",
                current_root_hashes={chains.root.key: chains.root.content_hash},
            )
            await session.commit()
            return result

    return await asyncio.gather(retry(), retry())


async def test_a_trial_branch_leaves_every_slot_unadopted(sessions, chains):
    await trial_branch(sessions, chains)

    slots = await all_slots(sessions)

    assert len(slots) == 4
    assert all(slot.source_candidate_id is None for slot in slots)


async def test_each_trial_candidate_can_be_adopted_into_its_stage(sessions, chains):
    branch = await trial_branch(sessions, chains)
    await adopt(sessions, chains, branch.final, "function", FINAL_STAGE)
    async with sessions() as session:
        final_slot = await stage_slot(session, chains.stages[FINAL_STAGE])
    for candidate, kind, stage in (
        (branch.material, "requirement_analysis", "extracting_text"),
        (branch.analysis, "function", "requirement_analysis"),
        (branch.points, "function", "case_names"),
    ):
        await adopt(sessions, chains, candidate, kind, stage)

    assert final_slot.source_candidate_id == branch.final.candidate_id
    assert slot_sources(await all_slots(sessions)) == {
        candidate.candidate_id
        for candidate in (branch.material, branch.analysis, branch.points, branch.final)
    }


async def test_continuation_rejects_a_source_replaced_after_adoption_and_queues_no_worker(
    sessions, chains
):
    branch = await trial_branch(sessions, chains)
    await adopt_branch(sessions, chains, branch)
    async with sessions() as session:
        point_token = (await stage_slot(session, chains.stages["case_names"])).content_token
    guarded = CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        required_current_source=SourceSelection(
            chain_kind="function",
            stage="case_names",
            source_kind="current",
            expected_current_token=point_token,
        ),
    )
    # A competing replacement lands after the adoption and before the continuation locks.
    async with sessions() as writer:
        await writer.execute(
            sa.update(AiGenerationStageContent)
            .where(AiGenerationStageContent.stage_id == chains.stages["case_names"])
            .values(content_token="replaced-before-continuation")
        )
        await writer.commit()

    async with sessions() as session:
        task = await session.scalar(
            sa.select(AiGenerateTask).where(
                AiGenerateTask.task_id == chains.tasks["function"]["task_id"]
            )
        )
        assert task is not None
        with pytest.raises(SourceClosureError, match="concurrent_change"):
            await dispatch_candidate_stage(
                session,
                task=task,
                kind="function",
                stage=FINAL_STAGE,
                actor_id="u",
                request=guarded,
                source=chains.function_source,
                direct_roots=(chains.root,),
                current_root_hashes={chains.root.key: chains.root.content_hash},
            )
        await session.rollback()
        queued = await session.scalar(
            sa.select(WorkerTask.task_id).where(WorkerTask.task_id == str(guarded.request_id))
        )
        candidates = await session.scalar(
            sa.select(sa.func.count()).select_from(AiGenerationCandidate)
        )

    assert queued is None
    assert slot_sources(await all_slots(sessions)) == {
        candidate.candidate_id
        for candidate in (branch.material, branch.analysis, branch.points, branch.final)
    }
    assert candidates == 4


async def test_concurrent_retries_of_one_adoption_apply_it_once(sessions, chains):
    branch = await trial_branch(sessions, chains)
    await adopt_branch(sessions, chains, branch)

    responses = await readopt_cases(sessions, chains, branch)

    async with sessions() as session:
        receipts = await session.scalar(
            sa.select(sa.func.count()).select_from(AiGenerationReviewReceipt)
        )
    assert sorted(result.replayed for result in responses) == [False, True]
    assert len({result.content_token for result in responses}) == 1
    assert receipts == 1


async def test_concurrent_retries_of_one_clear_clear_once_and_keep_the_candidates(sessions, chains):
    branch = await trial_branch(sessions, chains)
    await adopt_branch(sessions, chains, branch)
    responses = await readopt_cases(sessions, chains, branch)
    request = CurrentClearRequest(
        expected_current_token=responses[0].content_token, request_id=uuid4()
    )

    async def retry():
        async with sessions() as session:
            result = await clear_current_once(
                session,
                requirement_id="req",
                kind="function",
                stage=FINAL_STAGE,
                request=request,
                actor_id="u",
            )
            await session.commit()
            return result

    clears = await asyncio.gather(retry(), retry())

    async with sessions() as session:
        final_slot = await stage_slot(session, chains.stages[FINAL_STAGE])
        candidates = await session.scalar(
            sa.select(sa.func.count()).select_from(AiGenerationCandidate)
        )
    assert sorted(result.replayed for result in clears) == [False, True]
    assert len({result.content_token for result in clears}) == 1
    assert final_slot.source_candidate_id is None
    assert candidates == 4
