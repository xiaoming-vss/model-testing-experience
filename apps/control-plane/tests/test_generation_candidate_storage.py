"""The new storage constraints work independently of the legacy workflow."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.models import Base
from testing_agent.repositories.generation_candidate_storage import (
    CandidateEditSnapshot,
    clear_current_if_unchanged,
    dispose_candidate_if_unchanged,
    edit_unfrozen_candidate_if_unchanged,
    freeze_candidate_for_reference,
    get_stage_candidate,
    list_candidate_summaries,
    replace_current_if_unchanged,
)


@pytest.fixture
def storage(tmp_path):
    metadata = sa.MetaData()
    for name, key in (
        ("requirements", "requirement_id"),
        ("ai_generate_tasks", "task_id"),
        ("ai_generation_stages", "id"),
        ("ai_generation_attempts", "id"),
    ):
        sa.Table(name, metadata, sa.Column(key, sa.String(64), primary_key=True))
    names = (
        "requirement_generation_chains",
        "ai_generation_candidates",
        "ai_generation_stage_contents",
        "ai_generation_review_receipts",
    )
    for name in names:
        Base.metadata.tables[name].to_metadata(metadata)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'candidate-test.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        for name, values in (
            ("requirements", {"requirement_id": "r1"}),
            ("ai_generate_tasks", {"task_id": "task1"}),
            ("ai_generate_tasks", {"task_id": "task2"}),
            ("ai_generation_stages", {"id": "stage1"}),
            ("ai_generation_stages", {"id": "stage2"}),
            ("ai_generation_attempts", {"id": "attempt1"}),
        ):
            connection.execute(metadata.tables[name].insert().values(**values))
        connection.execute(
            metadata.tables[names[0]]
            .insert()
            .values(chain_id="chain1", requirement_id="r1", kind="function", task_id="task1")
        )
    yield engine, metadata
    engine.dispose()


def test_chain_and_current_are_unique_but_candidates_coexist(storage):
    engine, metadata = storage
    chain = metadata.tables["requirement_generation_chains"]
    candidate = metadata.tables["ai_generation_candidates"]
    current = metadata.tables["ai_generation_stage_contents"]
    with engine.begin() as connection:
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                chain.insert().values(
                    chain_id="chain2", requirement_id="r1", kind="function", task_id="task2"
                )
            )
        for value in ("a", "b", "c"):
            connection.execute(
                candidate.insert().values(
                    candidate_id=value,
                    snapshot_id=f"snapshot-{value}",
                    chain_id="chain1",
                    stage_id="stage1",
                    content=value,
                    format="text",
                    candidate_token=f"token-{value}",
                    disposition="available",
                    generation_mode="trial",
                    created_by="user",
                )
            )
        connection.execute(
            current.insert().values(
                stage_id="stage1", chain_id="chain1", stage="case_names", content_token="empty"
            )
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                current.insert().values(
                    stage_id="stage2",
                    chain_id="chain1",
                    stage="case_names",
                    content_token="duplicate",
                )
            )
        assert connection.scalar(sa.select(sa.func.count()).select_from(candidate)) == 3


def test_current_and_candidate_survive_attempt_cleanup(storage):
    engine, metadata = storage
    candidate = metadata.tables["ai_generation_candidates"]
    current = metadata.tables["ai_generation_stage_contents"]
    attempt = metadata.tables["ai_generation_attempts"]
    with engine.begin() as connection:
        connection.execute(
            candidate.insert().values(
                candidate_id="a",
                snapshot_id="snapshot-a",
                chain_id="chain1",
                stage_id="stage1",
                origin_attempt_id="attempt1",
                current_attempt_id="attempt1",
                content="retained",
                format="text",
                candidate_token="candidate-token",
                disposition="available",
                generation_mode="current",
                source_snapshot_json={"source": "snapshot"},
                created_by="user",
            )
        )
        connection.execute(
            current.insert().values(
                stage_id="stage1",
                chain_id="chain1",
                stage="case_names",
                content="retained",
                content_token="current-token",
                source_candidate_id="a",
                source_attempt_id="attempt1",
                source_snapshot_json={"source": "snapshot"},
                confirmed_at=datetime.now(UTC),
            )
        )
        connection.execute(attempt.delete().where(attempt.c.id == "attempt1"))
        assert connection.execute(
            sa.select(current.c.content, current.c.source_snapshot_json)
        ).one() == ("retained", {"source": "snapshot"})
        assert connection.scalar(sa.select(candidate.c.content)) == "retained"
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(candidate.delete().where(candidate.c.candidate_id == "a"))


def test_slot_tokens_prevent_stale_and_aba_updates(storage):
    engine, metadata = storage
    candidate = metadata.tables["ai_generation_candidates"]
    current = metadata.tables["ai_generation_stage_contents"]
    with engine.begin() as connection:
        for value in ("a", "b", "c"):
            connection.execute(
                candidate.insert().values(
                    candidate_id=value,
                    snapshot_id=f"snapshot-{value}",
                    chain_id="chain1",
                    stage_id="stage1",
                    content=value,
                    format="text",
                    candidate_token=f"candidate-{value}",
                    disposition="available",
                    generation_mode="trial",
                    created_by="user",
                )
            )
        connection.execute(
            current.insert().values(
                stage_id="stage1",
                chain_id="chain1",
                stage="case_names",
                content_token="empty-token",
            )
        )

    async def exercise():
        async_engine = create_async_engine(
            str(engine.url).replace("sqlite:", "sqlite+aiosqlite:", 1)
        )
        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        async with session_factory() as session:

            async def replace(expected, candidate_id, candidate_token=None):
                return await replace_current_if_unchanged(
                    session,
                    stage_id="stage1",
                    expected_content_token=expected,
                    candidate_id=candidate_id,
                    expected_candidate_token=candidate_token or f"candidate-{candidate_id}",
                    actor_id="user",
                    comment="",
                )

            token_a = await replace("empty-token", "a")
            assert token_a
            token_b = await replace(token_a, "b")
            assert token_b
            token_a_again = await replace(token_b, "a")
            assert token_a_again
            assert len({"empty-token", token_a, token_b, token_a_again}) == 4
            assert await replace(token_a, "b") is None
            assert await replace(token_a, "c") is None
            assert await replace(token_a_again, "b", "outdated-candidate") is None
            empty_again = await clear_current_if_unchanged(
                session, stage_id="stage1", expected_content_token=token_a_again
            )
            assert empty_again and empty_again not in {
                "empty-token",
                token_a,
                token_b,
                token_a_again,
            }
            assert await replace("empty-token", "a") is None
            assert (
                await clear_current_if_unchanged(
                    session, stage_id="stage1", expected_content_token=token_a_again
                )
                is None
            )
            frozen = dict(
                (
                    await session.execute(
                        sa.select(candidate.c.candidate_id, candidate.c.frozen_at)
                    )
                ).all()
            )
            assert frozen["a"] is not None and frozen["b"] is not None
            assert frozen["c"] is None
            row = (await session.execute(sa.select(current))).mappings().one()
            assert row["content"] is None and row["source_candidate_id"] is None
            assert row["content_token"] == empty_again
            await session.rollback()
        await async_engine.dispose()

    asyncio.run(exercise())
    with engine.connect() as connection:
        assert connection.scalar(sa.select(current.c.content_token)) == "empty-token"


def test_reference_freeze_and_edit_are_transactional(storage):
    engine, metadata = storage
    candidate = metadata.tables["ai_generation_candidates"]
    with engine.begin() as connection:
        connection.execute(
            candidate.insert().values(
                candidate_id="editable",
                snapshot_id="snapshot-original",
                chain_id="chain1",
                stage_id="stage1",
                current_attempt_id="attempt-original",
                content="original",
                format="text",
                candidate_token="token-original",
                disposition="available",
                generation_mode="trial",
                created_by="user",
            )
        )

    async def exercise():
        url = str(engine.url).replace("sqlite:", "sqlite+aiosqlite:", 1)
        async_engine = create_async_engine(url)
        factory = async_sessionmaker(async_engine, expire_on_commit=False)
        edit = CandidateEditSnapshot("attempt-edited", "edited", "text", None, "hash-edited")
        async with factory() as session:

            async def change(token, attempt):
                return await edit_unfrozen_candidate_if_unchanged(
                    session,
                    chain_id="chain1",
                    stage_id="stage1",
                    candidate_id="editable",
                    expected_candidate_token=token,
                    expected_attempt_id=attempt,
                    replacement=edit,
                )

            async def freeze(token, snapshot):
                return await freeze_candidate_for_reference(
                    session,
                    chain_id="chain1",
                    stage_id="stage1",
                    candidate_id="editable",
                    expected_candidate_token=token,
                    expected_snapshot_id=snapshot,
                )

            assert await change("token-original", "outdated-attempt") is None
            edited = await change("token-original", "attempt-original")
            assert edited is not None
            new_token, new_snapshot = edited
            assert new_token != "token-original" and new_snapshot != "snapshot-original"
            assert await freeze("token-original", "snapshot-original") is None
            assert await freeze(new_token, new_snapshot) is not None
            assert await change(new_token, "attempt-edited") is None
            await session.rollback()
        await async_engine.dispose()

    asyncio.run(exercise())
    with engine.connect() as connection:
        row = connection.execute(sa.select(candidate)).mappings().one()
        assert row["content"] == "original"
        assert row["frozen_at"] is None


def test_dispose_changes_only_target_and_cannot_dispose_current(storage):
    engine, metadata = storage
    candidate = metadata.tables["ai_generation_candidates"]
    current = metadata.tables["ai_generation_stage_contents"]
    with engine.begin() as connection:
        for value in ("a", "b", "c"):
            connection.execute(
                candidate.insert().values(
                    candidate_id=value,
                    snapshot_id=f"snapshot-{value}",
                    chain_id="chain1",
                    stage_id="stage1",
                    content=value,
                    format="text",
                    candidate_token=f"token-{value}",
                    disposition="available",
                    generation_mode="trial",
                    created_by="user",
                )
            )
        connection.execute(
            current.insert().values(
                stage_id="stage1",
                chain_id="chain1",
                stage="case_names",
                content_token="slot-token",
                source_candidate_id="a",
                content="a",
            )
        )

    async def exercise():
        url = str(engine.url).replace("sqlite:", "sqlite+aiosqlite:", 1)
        async_engine = create_async_engine(url)
        factory = async_sessionmaker(async_engine, expire_on_commit=False)
        async with factory() as session:

            async def dispose(value):
                return await dispose_candidate_if_unchanged(
                    session,
                    chain_id="chain1",
                    stage_id="stage1",
                    candidate_id=value,
                    expected_candidate_token=f"token-{value}",
                    disposition="rejected",
                )

            assert await dispose("a") is None
            token = await dispose("c")
            assert token and token != "token-c"
            assert await dispose("c") is None
            assert (
                await freeze_candidate_for_reference(
                    session,
                    chain_id="chain1",
                    stage_id="stage1",
                    candidate_id="c",
                    expected_candidate_token=token,
                    expected_snapshot_id="snapshot-c",
                )
                is None
            )
            rows = (
                await session.execute(sa.select(candidate.c.candidate_id, candidate.c.disposition))
            ).all()
            assert dict(rows) == {"a": "available", "b": "available", "c": "rejected"}
            row = (
                await session.execute(sa.select(current.c.source_candidate_id, current.c.content))
            ).one()
            assert row == ("a", "a")
            await session.commit()
        await async_engine.dispose()

    asyncio.run(exercise())


def test_candidate_list_is_bounded_and_does_not_load_bodies(storage):
    engine, metadata = storage
    candidate = metadata.tables["ai_generation_candidates"]
    current = metadata.tables["ai_generation_stage_contents"]
    with engine.begin() as connection:
        for index, value in enumerate(("a", "b", "c", "foreign")):
            connection.execute(
                candidate.insert().values(
                    candidate_id=value,
                    snapshot_id=f"snapshot-{value}",
                    chain_id="chain1",
                    stage_id="stage2" if value == "foreign" else "stage1",
                    content="private content",
                    source_snapshot_json={"secret": "private input"},
                    format="text",
                    candidate_token=f"token-{value}",
                    disposition="available",
                    generation_mode="trial",
                    created_by="user",
                    created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=index),
                )
            )
        connection.execute(
            current.insert().values(
                stage_id="stage1",
                chain_id="chain1",
                stage="case_names",
                content_token="slot-token",
                source_candidate_id="a",
                content="private content",
            )
        )

    async def exercise():
        url = str(engine.url).replace("sqlite:", "sqlite+aiosqlite:", 1)
        async_engine = create_async_engine(url)
        statements = []

        @sa.event.listens_for(async_engine.sync_engine, "before_cursor_execute")
        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lower())

        try:
            async with async_sessionmaker(async_engine, expire_on_commit=False)() as session:
                first, total = await list_candidate_summaries(
                    session, chain_id="chain1", stage_id="stage1", page=1, page_size=2
                )
                second, _ = await list_candidate_summaries(
                    session, chain_id="chain1", stage_id="stage1", page=2, page_size=2
                )
                assert total == 3
                assert [item.candidate_id for item in first] == ["c", "b"]
                assert [item.candidate_id for item in second] == ["a"]
                assert second[0].is_current and not any(item.is_current for item in first)
                assert all(
                    "ai_generation_candidates.content" not in statement for statement in statements
                )
                assert all("source_snapshot_json" not in statement for statement in statements)
                assert (
                    await get_stage_candidate(
                        session, chain_id="chain1", stage_id="stage1", candidate_id="foreign"
                    )
                    is None
                )
                detail = await get_stage_candidate(
                    session, chain_id="chain1", stage_id="stage1", candidate_id="a"
                )
                assert detail and detail.content == "private content"
                with pytest.raises(ValueError):
                    await list_candidate_summaries(
                        session, chain_id="chain1", stage_id="stage1", page=1, page_size=101
                    )
        finally:
            await async_engine.dispose()

    asyncio.run(exercise())
