"""Exercise candidate storage on an explicitly disposable MySQL database."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models import AiGenerationCandidate, AiGenerationStage, Base
from testing_agent.repositories.generation_candidate_creation import (
    CandidateProvenance,
    create_candidate_from_successful_attempt,
)
from testing_agent.repositories.generation_candidate_storage import (
    CandidateEditSnapshot,
    dispose_candidate_if_unchanged,
    edit_unfrozen_candidate_if_unchanged,
    freeze_candidate_for_reference,
    replace_current_if_unchanged,
)
from testing_agent.repositories.generation_current_chain import (
    ChainBindingConflict,
    bind_current_chain,
    delete_chain_storage_for_task,
    ensure_empty_slot,
)


def test_concurrent_creation_allows_one_chain_per_requirement_and_kind(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        requirement = seed_row(connection, tables["requirements"])
        task1 = seed_row(connection, tables["ai_generate_tasks"])
        task2 = seed_row(connection, tables["ai_generate_tasks"])
    chain = tables["requirement_generation_chains"]
    barrier = Barrier(2)

    def create_chain(number, task_id):
        try:
            with mysql.begin() as connection:
                barrier.wait(timeout=10)
                connection.execute(
                    chain.insert().values(
                        chain_id=f"concurrent-{number}",
                        requirement_id=requirement["requirement_id"],
                        kind="function",
                        task_id=task_id,
                    )
                )
            return "created"
        except IntegrityError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda args: create_chain(*args), [(1, task1["task_id"]), (2, task2["task_id"])]
            )
        )
    assert sorted(results) == ["created", "duplicate"]
    with mysql.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(chain)
                .where(
                    chain.c.requirement_id == requirement["requirement_id"],
                    chain.c.kind == "function",
                )
            )
            == 1
        )


def test_retained_content_survives_attempt_deletion(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        requirement = seed_row(connection, tables["requirements"])
        task = seed_row(connection, tables["ai_generate_tasks"])
        stage = seed_row(connection, tables["ai_generation_stages"], {"task_id": task["task_id"]})
        attempt = seed_row(connection, tables["ai_generation_attempts"], {"stage_id": stage["id"]})
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
        for suffix in ("a", "b", "c"):
            seed_row(
                connection,
                candidate,
                {
                    "candidate_id": f"candidate-{suffix}",
                    "chain_id": chain["chain_id"],
                    "stage_id": stage["id"],
                    "origin_attempt_id": attempt["id"] if suffix == "a" else None,
                    "current_attempt_id": attempt["id"] if suffix == "a" else None,
                    "content": suffix,
                    "source_snapshot_json": {"input": "saved"},
                },
            )
        current = tables["ai_generation_stage_contents"]
        seed_row(
            connection,
            current,
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "case_names",
                "content": "a",
                "source_candidate_id": "candidate-a",
                "source_attempt_id": attempt["id"],
                "source_snapshot_json": {"input": "saved"},
            },
        )
        connection.execute(
            tables["ai_generation_attempts"]
            .delete()
            .where(tables["ai_generation_attempts"].c.id == attempt["id"])
        )
        assert connection.execute(
            sa.select(current.c.content, current.c.source_snapshot_json)
        ).one() == ("a", {"input": "saved"})
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(candidate)
                .where(candidate.c.stage_id == stage["id"])
            )
            == 3
        )


def test_concurrent_current_updates_reject_stale_token(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        requirement = seed_row(connection, tables["requirements"])
        task = seed_row(connection, tables["ai_generate_tasks"])
        stage = seed_row(connection, tables["ai_generation_stages"], {"task_id": task["task_id"]})
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "api",
            },
        )
        for value in ("a", "b"):
            seed_row(
                connection,
                tables["ai_generation_candidates"],
                {
                    "candidate_id": f"cas-{value}",
                    "chain_id": chain["chain_id"],
                    "stage_id": stage["id"],
                    "candidate_token": f"candidate-{value}",
                    "disposition": "available",
                    "content": value,
                },
            )
        seed_row(
            connection,
            tables["ai_generation_stage_contents"],
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "api_design",
                "content_token": "initial-token",
            },
        )

    async def exercise():
        url = mysql.url.set(drivername="mysql+asyncmy").render_as_string(hide_password=False)
        async_engine = create_async_engine(url)
        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

        async def replace(value):
            async with session_factory() as session:
                token = await replace_current_if_unchanged(
                    session,
                    stage_id=stage["id"],
                    expected_content_token="initial-token",
                    candidate_id=f"cas-{value}",
                    expected_candidate_token=f"candidate-{value}",
                    actor_id="user",
                    comment="",
                )
                await session.commit()
                return token

        try:
            return await asyncio.gather(replace("a"), replace("b"))
        finally:
            await async_engine.dispose()

    results = asyncio.run(exercise())
    assert sum(result is not None for result in results) == 1
    with mysql.connect() as connection:
        current = tables["ai_generation_stage_contents"]
        row = (
            connection.execute(sa.select(current).where(current.c.stage_id == stage["id"]))
            .mappings()
            .one()
        )
        assert row["content"] in {"a", "b"}
        assert row["content_token"] in results


def test_reference_and_edit_race_has_one_winner(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        requirement = seed_row(connection, tables["requirements"])
        task = seed_row(connection, tables["ai_generate_tasks"])
        stage = seed_row(connection, tables["ai_generation_stages"], {"task_id": task["task_id"]})
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "api",
            },
        )
        seed_row(
            connection,
            tables["ai_generation_candidates"],
            {
                "candidate_id": "race-candidate",
                "snapshot_id": "original-snapshot",
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "current_attempt_id": "original-attempt",
                "candidate_token": "original-token",
                "disposition": "available",
                "content": "original",
            },
        )

    async def exercise():
        url = mysql.url.set(drivername="mysql+asyncmy").render_as_string(hide_password=False)
        async_engine = create_async_engine(url)
        factory = async_sessionmaker(async_engine, expire_on_commit=False)
        start = asyncio.Event()

        async def freeze():
            async with factory() as session:
                await start.wait()
                result = await freeze_candidate_for_reference(
                    session,
                    chain_id=chain["chain_id"],
                    stage_id=stage["id"],
                    candidate_id="race-candidate",
                    expected_candidate_token="original-token",
                    expected_snapshot_id="original-snapshot",
                )
                await session.commit()
                return result is not None

        async def edit():
            async with factory() as session:
                await start.wait()
                result = await edit_unfrozen_candidate_if_unchanged(
                    session,
                    chain_id=chain["chain_id"],
                    stage_id=stage["id"],
                    candidate_id="race-candidate",
                    expected_candidate_token="original-token",
                    expected_attempt_id="original-attempt",
                    replacement=CandidateEditSnapshot(
                        "edited-attempt", "edited", "text", None, "hash"
                    ),
                )
                await session.commit()
                return result is not None

        try:
            tasks = [asyncio.create_task(freeze()), asyncio.create_task(edit())]
            start.set()
            return await asyncio.gather(*tasks)
        finally:
            await async_engine.dispose()

    frozen, edited = asyncio.run(exercise())
    assert frozen != edited
    with mysql.connect() as connection:
        candidate = tables["ai_generation_candidates"]
        row = (
            connection.execute(
                sa.select(candidate).where(candidate.c.candidate_id == "race-candidate")
            )
            .mappings()
            .one()
        )
        if frozen:
            assert row["frozen_at"] is not None
            assert row["snapshot_id"] == "original-snapshot" and row["content"] == "original"
        else:
            assert row["frozen_at"] is None
            assert row["snapshot_id"] != "original-snapshot" and row["content"] == "edited"


def test_disposal_and_adoption_race_cannot_reject_current(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        requirement = seed_row(connection, tables["requirements"])
        task = seed_row(connection, tables["ai_generate_tasks"])
        stage = seed_row(connection, tables["ai_generation_stages"], {"task_id": task["task_id"]})
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "api",
            },
        )
        seed_row(
            connection,
            tables["ai_generation_candidates"],
            {
                "candidate_id": "disposition-race",
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "candidate_token": "original-token",
                "disposition": "available",
                "content": "original",
            },
        )
        seed_row(
            connection,
            tables["ai_generation_stage_contents"],
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "api_design",
                "content_token": "slot-token",
            },
        )

    async def exercise():
        url = mysql.url.set(drivername="mysql+asyncmy").render_as_string(hide_password=False)
        async_engine = create_async_engine(url)
        factory = async_sessionmaker(async_engine, expire_on_commit=False)
        start = asyncio.Event()

        async def adopt():
            async with factory() as session:
                await start.wait()
                result = await replace_current_if_unchanged(
                    session,
                    stage_id=stage["id"],
                    candidate_id="disposition-race",
                    expected_content_token="slot-token",
                    expected_candidate_token="original-token",
                    actor_id="user",
                    comment="",
                )
                await session.commit()
                return result is not None

        async def reject():
            async with factory() as session:
                await start.wait()
                result = await dispose_candidate_if_unchanged(
                    session,
                    chain_id=chain["chain_id"],
                    stage_id=stage["id"],
                    candidate_id="disposition-race",
                    expected_candidate_token="original-token",
                    disposition="rejected",
                )
                await session.commit()
                return result is not None

        try:
            tasks = [asyncio.create_task(adopt()), asyncio.create_task(reject())]
            start.set()
            return await asyncio.gather(*tasks)
        finally:
            await async_engine.dispose()

    adopted, rejected = asyncio.run(exercise())
    assert adopted != rejected
    with mysql.connect() as connection:
        candidate = tables["ai_generation_candidates"]
        current = tables["ai_generation_stage_contents"]
        row = connection.execute(
            sa.select(candidate.c.disposition, current.c.source_candidate_id)
            .join(current, candidate.c.stage_id == current.c.stage_id)
            .where(
                candidate.c.candidate_id == "disposition-race", current.c.stage_id == stage["id"]
            )
        ).one()
        assert row == (("available", "disposition-race") if adopted else ("rejected", None))


def test_adoption_refreshes_candidate_cached_before_edit(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        requirement = seed_row(connection, tables["requirements"])
        task = seed_row(connection, tables["ai_generate_tasks"])
        stage = seed_row(connection, tables["ai_generation_stages"], {"task_id": task["task_id"]})
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "api",
            },
        )
        seed_row(
            connection,
            tables["ai_generation_candidates"],
            {
                "candidate_id": "cached-candidate",
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "candidate_token": "original-token",
                "current_attempt_id": "original-attempt",
                "disposition": "available",
                "content": "original",
                "format": "text",
            },
        )
        seed_row(
            connection,
            tables["ai_generation_stage_contents"],
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "api_design",
                "content_token": "slot-token",
            },
        )

    async def exercise():
        url = mysql.url.set(drivername="mysql+asyncmy").render_as_string(hide_password=False)
        async_engine = create_async_engine(url)
        factory = async_sessionmaker(async_engine, expire_on_commit=False)
        try:
            async with factory() as reader, factory() as editor:
                cached = await reader.get(AiGenerationCandidate, "cached-candidate")
                assert cached and cached.content == "original"
                changed = await edit_unfrozen_candidate_if_unchanged(
                    editor,
                    chain_id=chain["chain_id"],
                    stage_id=stage["id"],
                    candidate_id="cached-candidate",
                    expected_candidate_token="original-token",
                    expected_attempt_id="original-attempt",
                    replacement=CandidateEditSnapshot(
                        "edited-attempt", "edited", "text", None, "edited-hash"
                    ),
                )
                assert changed
                await editor.commit()
                result = await replace_current_if_unchanged(
                    reader,
                    stage_id=stage["id"],
                    candidate_id="cached-candidate",
                    expected_candidate_token=changed[0],
                    expected_content_token="slot-token",
                    actor_id="user",
                    comment="",
                )
                assert result
                await reader.commit()
        finally:
            await async_engine.dispose()

    asyncio.run(exercise())
    with mysql.connect() as connection:
        current = tables["ai_generation_stage_contents"]
        row = connection.execute(
            sa.select(current.c.content, current.c.content_hash).where(
                current.c.stage_id == stage["id"]
            )
        ).one()
        assert row == ("edited", "edited-hash")


def test_scoped_chain_binding_and_empty_slot_under_concurrency(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection, tables["requirements"], {"sprint_id": sprint["sprint_id"]}
        )
        scope = {
            "project_id": project["project_id"],
            "sprint_id": sprint["sprint_id"],
            "requirement_id": requirement["requirement_id"],
            "task_type": "functional_case_generate",
        }
        task1 = seed_row(connection, tables["ai_generate_tasks"], scope)
        task2 = seed_row(connection, tables["ai_generate_tasks"], scope)

    async def exercise():
        url = mysql.url.set(drivername="mysql+asyncmy").render_as_string(hide_password=False)
        engine = create_async_engine(url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        start = asyncio.Event()

        async def bind(task_id):
            async with factory() as session:
                await start.wait()
                try:
                    chain = await bind_current_chain(
                        session,
                        requirement_id=requirement["requirement_id"],
                        kind="function",
                        task_id=task_id,
                    )
                    result = chain.chain_id, chain.task_id
                    await session.commit()
                    return result
                except ChainBindingConflict:
                    await session.rollback()
                    return None

        try:
            tasks = [
                asyncio.create_task(bind(task1["task_id"])),
                asyncio.create_task(bind(task2["task_id"])),
            ]
            start.set()
            results = await asyncio.gather(*tasks)
            winners = [result for result in results if result]
            assert len(winners) == 1
            chain_id, task_id = winners[0]
            async with factory() as session:
                stage = AiGenerationStage(
                    id="binding-race-stage", task_id=task_id, stage="case_names"
                )
                session.add(stage)
                await session.commit()

            async def slot():
                async with factory() as session:
                    row = await ensure_empty_slot(
                        session, chain_id=chain_id, stage_id="binding-race-stage"
                    )
                    token = row.content_token
                    await session.commit()
                    return token

            tokens = await asyncio.gather(slot(), slot())
            assert tokens[0] and tokens[0] == tokens[1]
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_successful_attempt_replay_creates_only_one_candidate(mysql):  # noqa: F811
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
        attempt = seed_row(
            connection,
            tables["ai_generation_attempts"],
            {
                "stage_id": stage["id"],
                "status": "success",
                "output_content": '{"a": 1}',
                "output_format": "json",
                "requested_by": "u",
            },
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

    async def exercise():
        url = mysql.url.set(drivername="mysql+asyncmy").render_as_string(hide_password=False)
        engine = create_async_engine(url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        start = asyncio.Event()

        async def create():
            async with factory() as session:
                await start.wait()
                candidate = await create_candidate_from_successful_attempt(
                    session,
                    chain_id=chain["chain_id"],
                    stage_id=stage["id"],
                    attempt_id=attempt["id"],
                    provenance=CandidateProvenance("current", {"sources": []}, "lineage", "basis"),
                )
                candidate_id = candidate.candidate_id
                await session.commit()
                return candidate_id

        try:
            tasks = [asyncio.create_task(create()), asyncio.create_task(create())]
            start.set()
            return await asyncio.gather(*tasks)
        finally:
            await engine.dispose()

    ids = asyncio.run(exercise())
    assert ids[0] == ids[1]
    with mysql.connect() as connection:
        candidate = tables["ai_generation_candidates"]
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(candidate)
                .where(
                    candidate.c.stage_id == stage["id"],
                    candidate.c.origin_attempt_id == attempt["id"],
                )
            )
            == 1
        )


def test_task_storage_cleanup_keeps_formal_assets(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        requirement = seed_row(connection, tables["requirements"])
        task = seed_row(connection, tables["ai_generate_tasks"])
        stage = seed_row(connection, tables["ai_generation_stages"], {"task_id": task["task_id"]})
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "function",
            },
        )
        suite = seed_row(
            connection,
            tables["function_test_suites"],
            {"requirement_id": requirement["requirement_id"]},
        )
        candidate = tables["ai_generation_candidates"]
        seed_row(
            connection,
            candidate,
            {
                "candidate_id": "delete-parent",
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
            },
        )
        seed_row(
            connection,
            candidate,
            {
                "candidate_id": "delete-child",
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "derived_from_candidate_id": "delete-parent",
            },
        )
        seed_row(
            connection,
            tables["ai_generation_stage_contents"],
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "case_names",
                "source_candidate_id": "delete-parent",
            },
        )

    async def exercise():
        url = mysql.url.set(drivername="mysql+asyncmy").render_as_string(hide_password=False)
        engine = create_async_engine(url)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                await delete_chain_storage_for_task(session, task_id=task["task_id"])
                await session.execute(
                    tables["ai_generate_tasks"]
                    .delete()
                    .where(tables["ai_generate_tasks"].c.task_id == task["task_id"])
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    with mysql.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(candidate)
                .where(candidate.c.chain_id == chain["chain_id"])
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.select(tables["function_test_suites"].c.suite_id).where(
                    tables["function_test_suites"].c.suite_id == suite["suite_id"]
                )
            )
            == suite["suite_id"]
        )
