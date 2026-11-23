"""Candidate disposition concurrency on an explicitly disposable MySQL database."""

import asyncio
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.generation import generation_services
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models import AiGenerationAttempt, AiGenerationStage, Base
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_candidate_storage import freeze_candidate_for_reference
from testing_agent.schemas.generation_candidates import (
    CandidateDeriveRequest,
    CandidateDispositionRequest,
    CandidateEditRequest,
)
from testing_agent.services.generation_candidate_commands import CandidateCommands
from testing_agent.services.generation_candidate_queries import CandidateQueries


def test_concurrent_rejection_replays_one_receipt(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection, tables["requirements"], {"sprint_id": sprint["sprint_id"]}
        )
        task = seed_row(
            connection,
            tables["ai_generate_tasks"],
            {
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
                "task_type": "functional_case_generate",
            },
        )
        stage = seed_row(
            connection,
            tables["ai_generation_stages"],
            {"task_id": task["task_id"], "stage": "case_names"},
        )
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "function",
            },
        )
        candidate = tables["ai_generation_candidates"]
        for value in ("current", "reject"):
            seed_row(
                connection,
                candidate,
                {
                    "candidate_id": f"command-{value}",
                    "chain_id": chain["chain_id"],
                    "stage_id": stage["id"],
                    "candidate_token": f"token-{value}",
                    "disposition": "available",
                    "generation_mode": "current",
                    "created_by": project["user_id"],
                },
            )
        seed_row(
            connection,
            tables["ai_generation_stage_contents"],
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "case_names",
                "source_candidate_id": "command-current",
                "content_token": "slot-token",
            },
        )

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        start = asyncio.Event()
        body = CandidateDispositionRequest(
            action="reject",
            expectedCandidateToken="token-reject",
            requestId=uuid4(),
            comment="review",
        )

        async def reject():
            async with factory() as session:
                await start.wait()
                service = generation_services(AiGenerateTaskRepository(session)).chain
                return await CandidateCommands(service).dispose(
                    requirement["requirement_id"],
                    "function",
                    "case_names",
                    "command-reject",
                    body,
                    project["user_id"],
                )

        try:
            tasks = [asyncio.create_task(reject()) for _ in range(3)]
            start.set()
            return await asyncio.gather(*tasks)
        finally:
            await engine.dispose()

    results = asyncio.run(exercise())
    assert len({result.candidate_token for result in results}) == 1
    with mysql.connect() as connection:
        receipt = tables["ai_generation_review_receipts"]
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(receipt)
                .where(receipt.c.candidate_id == "command-reject")
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(candidate.c.disposition).where(
                    candidate.c.candidate_id == "command-reject"
                )
            )
            == "rejected"
        )
        assert (
            connection.scalar(
                sa.select(tables["ai_generation_stage_contents"].c.source_candidate_id).where(
                    tables["ai_generation_stage_contents"].c.stage_id == stage["id"]
                )
            )
            == "command-current"
        )


def test_edit_and_reference_freeze_cannot_both_win(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection, tables["requirements"], {"sprint_id": sprint["sprint_id"]}
        )
        task = seed_row(
            connection,
            tables["ai_generate_tasks"],
            {
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
                "task_type": "api_case_generate",
            },
        )
        stage = seed_row(
            connection,
            tables["ai_generation_stages"],
            {"task_id": task["task_id"], "stage": "interface_extract"},
        )
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "api",
            },
        )
        attempt = seed_row(
            connection,
            tables["ai_generation_attempts"],
            {
                "stage_id": stage["id"],
                "attempt_no": 1,
                "status": "success",
                "output_content": '{"interfaces": {}}',
                "output_format": "json",
            },
        )
        candidate = tables["ai_generation_candidates"]
        seed_row(
            connection,
            candidate,
            {
                "candidate_id": "edit-race",
                "snapshot_id": "edit-snapshot",
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "current_attempt_id": attempt["id"],
                "candidate_token": "edit-token",
                "disposition": "available",
                "generation_mode": "trial",
                "created_by": project["user_id"],
                "content": '{"interfaces": {}}',
                "format": "json",
                "source_snapshot_json": {"source": {}},
            },
        )
        seed_row(
            connection,
            tables["ai_generation_stage_contents"],
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "interface_extract",
                "content_token": "slot-token",
            },
        )

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        start = asyncio.Event()

        async def edit():
            async with factory() as session:
                await start.wait()
                service = generation_services(AiGenerateTaskRepository(session)).chain
                body = CandidateEditRequest(
                    expectedCandidateToken="edit-token",
                    expectedAttemptId=attempt["id"],
                    content='{"interfaces": {"login": {}}}',
                )
                try:
                    await CandidateCommands(service).edit(
                        requirement["requirement_id"],
                        "api",
                        "interface_extract",
                        "edit-race",
                        body,
                        project["user_id"],
                    )
                    return True
                except AppError:
                    await session.rollback()
                    return False

        async def freeze():
            async with factory() as session:
                await start.wait()
                result = await freeze_candidate_for_reference(
                    session,
                    chain_id=chain["chain_id"],
                    stage_id=stage["id"],
                    candidate_id="edit-race",
                    expected_candidate_token="edit-token",
                    expected_snapshot_id="edit-snapshot",
                )
                await session.commit()
                return result is not None

        try:
            tasks = [asyncio.create_task(edit()), asyncio.create_task(freeze())]
            start.set()
            return await asyncio.gather(*tasks)
        finally:
            await engine.dispose()

    edited, frozen = asyncio.run(exercise())
    assert edited != frozen
    with mysql.connect() as connection:
        row = (
            connection.execute(sa.select(candidate).where(candidate.c.candidate_id == "edit-race"))
            .mappings()
            .one()
        )
        if edited:
            assert "login" in row["content"] and row["frozen_at"] is None
            assert row["snapshot_id"] != "edit-snapshot"
        else:
            assert row["content"] == '{"interfaces": {}}' and row["frozen_at"] is not None


def test_edit_allocates_attempt_number_from_current_read(mysql, monkeypatch):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection, tables["requirements"], {"sprint_id": sprint["sprint_id"]}
        )
        task = seed_row(
            connection,
            tables["ai_generate_tasks"],
            {
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
                "task_type": "api_case_generate",
            },
        )
        stage = seed_row(
            connection,
            tables["ai_generation_stages"],
            {"task_id": task["task_id"], "stage": "interface_extract"},
        )
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "api",
            },
        )
        attempt = seed_row(
            connection,
            tables["ai_generation_attempts"],
            {
                "stage_id": stage["id"],
                "attempt_no": 1,
                "status": "success",
                "output_content": '{"interfaces": {}}',
                "output_format": "json",
            },
        )
        seed_row(
            connection,
            tables["ai_generation_candidates"],
            {
                "candidate_id": "sequence-candidate",
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "current_attempt_id": attempt["id"],
                "candidate_token": "sequence-token",
                "disposition": "available",
                "generation_mode": "trial",
                "created_by": project["user_id"],
                "content": '{"interfaces": {}}',
                "format": "json",
                "source_snapshot_json": {"source": {}},
            },
        )
        seed_row(
            connection,
            tables["ai_generation_stage_contents"],
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "interface_extract",
                "content_token": "sequence-slot",
            },
        )

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        scoped = asyncio.Event()
        original = CandidateQueries.scope

        async def signal_scope(self, *args, **kwargs):
            result = await original(self, *args, **kwargs)
            scoped.set()
            return result

        monkeypatch.setattr(CandidateQueries, "scope", signal_scope)
        try:
            async with factory() as worker, factory() as editor:
                await worker.scalar(
                    sa.select(AiGenerationStage)
                    .where(AiGenerationStage.id == stage["id"])
                    .with_for_update()
                )
                service = generation_services(AiGenerateTaskRepository(editor)).chain
                body = CandidateEditRequest(
                    expectedCandidateToken="sequence-token",
                    expectedAttemptId=attempt["id"],
                    content='{"interfaces": {"login": {}}}',
                )
                editing = asyncio.create_task(
                    CandidateCommands(service).edit(
                        requirement["requirement_id"],
                        "api",
                        "interface_extract",
                        "sequence-candidate",
                        body,
                        project["user_id"],
                    )
                )
                await asyncio.wait_for(scoped.wait(), timeout=10)
                worker.add(
                    AiGenerationAttempt(
                        id="concurrent-attempt",
                        stage_id=stage["id"],
                        attempt_no=2,
                        operation="generate",
                        status="success",
                        invalidated_reason="",
                    )
                )
                await worker.commit()
                result = await asyncio.wait_for(editing, timeout=10)
                return result.current_attempt_id
        finally:
            await engine.dispose()

    attempt_id = asyncio.run(exercise())
    with mysql.connect() as connection:
        attempts = tables["ai_generation_attempts"]
        assert (
            connection.scalar(sa.select(attempts.c.attempt_no).where(attempts.c.id == attempt_id))
            == 3
        )


def test_concurrent_derive_replays_one_candidate(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection, tables["requirements"], {"sprint_id": sprint["sprint_id"]}
        )
        task = seed_row(
            connection,
            tables["ai_generate_tasks"],
            {
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
                "task_type": "api_case_generate",
            },
        )
        stage = seed_row(
            connection,
            tables["ai_generation_stages"],
            {"task_id": task["task_id"], "stage": "interface_extract"},
        )
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "api",
            },
        )
        attempt = seed_row(
            connection,
            tables["ai_generation_attempts"],
            {
                "stage_id": stage["id"],
                "attempt_no": 1,
                "status": "success",
                "output_content": '{"interfaces": {}}',
                "output_format": "json",
            },
        )
        candidate = tables["ai_generation_candidates"]
        seed_row(
            connection,
            candidate,
            {
                "candidate_id": "derive-parent",
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "current_attempt_id": attempt["id"],
                "candidate_token": "parent-token",
                "disposition": "available",
                "generation_mode": "trial",
                "created_by": project["user_id"],
                "content": '{"interfaces": {}}',
                "format": "json",
                "source_snapshot_json": {"source": {}},
            },
        )
        seed_row(
            connection,
            tables["ai_generation_stage_contents"],
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "interface_extract",
                "source_candidate_id": "derive-parent",
                "content_token": "slot-token",
            },
        )

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        start = asyncio.Event()
        body = CandidateDeriveRequest(
            expectedCandidateToken="parent-token",
            expectedAttemptId=attempt["id"],
            content='{"interfaces": {"derived": {}}}',
            requestId=uuid4(),
        )

        async def derive():
            async with factory() as session:
                await start.wait()
                service = generation_services(AiGenerateTaskRepository(session)).chain
                return await CandidateCommands(service).derive(
                    requirement["requirement_id"],
                    "api",
                    "interface_extract",
                    "derive-parent",
                    body,
                    project["user_id"],
                )

        try:
            tasks = [asyncio.create_task(derive()) for _ in range(3)]
            start.set()
            return await asyncio.gather(*tasks)
        finally:
            await engine.dispose()

    results = asyncio.run(exercise())
    assert len({result.candidate_id for result in results}) == 1
    assert len({result.snapshot_id for result in results}) == 1
    with mysql.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(candidate)
                .where(candidate.c.derived_from_candidate_id == "derive-parent")
            )
            == 1
        )
        receipt = tables["ai_generation_review_receipts"]
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(receipt)
                .where(receipt.c.candidate_id == "derive-parent", receipt.c.decision == "derived")
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(tables["ai_generation_stage_contents"].c.source_candidate_id).where(
                    tables["ai_generation_stage_contents"].c.stage_id == stage["id"]
                )
            )
            == "derive-parent"
        )
