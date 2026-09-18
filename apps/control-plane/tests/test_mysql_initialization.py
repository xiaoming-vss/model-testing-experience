"""Run against an explicitly supplied empty, disposable MySQL database."""

import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from test_initial_schema_migration import assert_current_schema, migration_config

from alembic import command
from testing_agent.models import Base


@pytest.fixture(scope="module")
def mysql():
    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set CONTROL_PLANE_TEST_DATABASE_URL to an empty disposable MySQL database")
    engine = sa.create_engine(url)
    assert engine.dialect.name == "mysql"
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.connect() as connection:
        assert sa.inspect(connection).get_table_names() == [], "Test database must be empty"
        config = migration_config(connection)
        command.upgrade(config, "head")
        connection.commit()
        yield engine
        command.downgrade(config, "base")
        connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.commit()
    engine.dispose()


def test_mysql_baseline_and_roundtrip(mysql):
    with mysql.connect() as connection:
        config = migration_config(connection)
        assert_current_schema(connection)
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        assert sa.inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        assert_current_schema(connection)
        connection.commit()


def seed_row(connection, table, overrides=None):
    """Populate required columns and real parent rows for constraint tests."""
    values = {}
    for col in table.columns:
        if col.computed is not None or col.nullable or col.default is not None:
            continue
        if col.primary_key and isinstance(col.type, sa.Integer):
            continue
        if col.foreign_keys:
            parent = next(iter(col.foreign_keys)).column
            values[col.name] = seed_row(connection, parent.table)[parent.name]
        elif isinstance(col.type, sa.DateTime):
            values[col.name] = datetime.now(UTC)
        elif isinstance(col.type, sa.Date):
            values[col.name] = date.today()
        elif isinstance(col.type, sa.Boolean):
            values[col.name] = False
        elif isinstance(col.type, sa.Integer):
            values[col.name] = 1
        elif isinstance(col.type, sa.JSON):
            values[col.name] = {}
        else:
            values[col.name] = uuid4().hex[: min(getattr(col.type, "length", None) or 32, 32)]
    if table.name == "project_members":
        values["role"] = "member"
    if table.name == "sprints":
        values["end_time"] = values["start_time"] + timedelta(days=1)
    values.update(overrides or {})
    result = connection.execute(table.insert().values(**values))
    for key, value in zip(
        table.primary_key.columns.keys(), result.inserted_primary_key, strict=True
    ):
        values[key] = value
    return values


UNIQUE_TABLES = [
    table.name
    for table in Base.metadata.tables.values()
    if any(
        isinstance(c, sa.UniqueConstraint) and str(c.name).startswith("uk_")
        for c in table.constraints
    )
]


@pytest.mark.parametrize("name", UNIQUE_TABLES)
def test_mysql_business_uniqueness_requires_hard_delete(mysql, name):
    table = Base.metadata.tables[name]
    constraint = next(
        c
        for c in table.constraints
        if isinstance(c, sa.UniqueConstraint) and str(c.name).startswith("uk_")
    )
    with mysql.connect() as connection:
        first = seed_row(connection, table)
        business_key = {c.name: first[c.name] for c in constraint.columns}
        with pytest.raises(IntegrityError):
            seed_row(connection, table, business_key)
        connection.execute(table.delete().where(table.c.id == first["id"]))
        seed_row(connection, table, business_key)
        connection.rollback()


@pytest.mark.parametrize(
    ("local_kind", "remote_kind"), [("project", "group"), ("requirement", "repository")]
)
def test_mysql_concurrent_gitlab_binding_conflict(mysql, local_kind, remote_kind):
    table = Base.metadata.tables["resource_bindings"]
    key = dict(
        provider="gitlab",
        local_resource_type=local_kind,
        local_resource_id="local",
        remote_resource_type=remote_kind,
        remote_resource_id="remote",
        status="active",
    )
    # Both writers can pass a pre-check; only the database can arbitrate the insert race.
    with mysql.connect() as first, mysql.connect() as second:
        assert first.execute(sa.select(table.c.id)).first() is None
        assert second.execute(sa.select(table.c.id)).first() is None
        row = seed_row(first, table, key)
        first.commit()
        with pytest.raises(IntegrityError) as error:
            seed_row(second, table, key)
        assert "uq_binding_resource" in str(error.value.orig)
        second.rollback()
        first.execute(table.delete().where(table.c.id == row["id"]))
        first.commit()


async def test_group_delete_waits_for_requirement_binding_and_then_rejects(mysql):
    import asyncio
    import time

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from testing_agent.core.errors import AppError, ErrGroupBindingInUse
    from testing_agent.repositories.resource_binding import ResourceBindingRepository
    from testing_agent.services.resource_binding import ResourceBindingService

    with mysql.begin() as connection:
        seed_row(connection, Base.metadata.tables["users"], {"user_id": "user"})
        seed_row(
            connection,
            Base.metadata.tables["projects"],
            {"project_id": "race-project", "user_id": "user"},
        )
        seed_row(
            connection,
            Base.metadata.tables["sprints"],
            {"sprint_id": "race-sprint", "project_id": "race-project"},
        )
        seed_row(
            connection,
            Base.metadata.tables["requirements"],
            {"requirement_id": "race-req", "sprint_id": "race-sprint"},
        )
        seed_row(
            connection,
            Base.metadata.tables["resource_bindings"],
            {
                "binding_id": "race-group",
                "instance_url": "https://gitlab.example",
                "instance_key": __import__("hashlib").sha256(b"https://gitlab.example").hexdigest(),
                "provider": "gitlab",
                "local_resource_type": "project",
                "local_resource_id": "race-project",
                "remote_resource_type": "group",
                "remote_resource_id": "7",
                "connection_id": "connection",
                "status": "active",
            },
        )

    validating, release, deleting = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Connections:
        async def resolve_personal_connection(
            self, user_id, provider, project_id, instance_url, connection_id=""
        ):
            from types import SimpleNamespace

            assert user_id == "user"
            return SimpleNamespace(connection_id="connection", base_url=instance_url)

        async def ensure_gitlab_repository_scope(self, *args, **kwargs):
            validating.set()
            await release.wait()
            return "11"

    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    deletion_connection_id = None

    async def create():
        async with sessions() as session:
            return await ResourceBindingService(
                ResourceBindingRepository(session), Connections()
            ).create(
                "requirement",
                "race-req",
                {
                    "provider": "gitlab",
                    "remoteResourceId": "11",
                    "remoteParentId": "7",
                    "extraJson": {"branch": "main"},
                },
                "user",
            )

    async def delete():
        nonlocal deletion_connection_id
        async with sessions() as session:
            deletion_connection_id = await session.scalar(sa.text("SELECT CONNECTION_ID()"))
            deleting.set()
            return await ResourceBindingService(ResourceBindingRepository(session)).delete(
                "project",
                "race-project",
                "race-group",
                "user",
            )

    creating = asyncio.create_task(create())
    deletion = None
    try:
        await asyncio.wait_for(validating.wait(), timeout=5)
        deletion = asyncio.create_task(delete())
        await asyncio.wait_for(deleting.wait(), timeout=5)
        deadline = time.monotonic() + 5
        with mysql.connect() as connection:
            while True:
                assert not deletion.done(), "Group deletion escaped the shared group lock"
                waiting = connection.scalar(
                    sa.text(
                        "SELECT COUNT(*) FROM performance_schema.data_lock_waits w "
                        "JOIN performance_schema.threads t ON t.THREAD_ID = w.REQUESTING_THREAD_ID "
                        "WHERE t.PROCESSLIST_ID = :id"
                    ),
                    {"id": deletion_connection_id},
                )
                if waiting:
                    break
                assert time.monotonic() < deadline, "Group deletion did not wait on the group lock"
                await asyncio.sleep(0.02)
        release.set()
        await asyncio.wait_for(creating, timeout=5)
        with pytest.raises(AppError) as error:
            await asyncio.wait_for(deletion, timeout=5)
        assert error.value.code == ErrGroupBindingInUse.code
        with mysql.connect() as connection:
            table = Base.metadata.tables["resource_bindings"]
            assert (
                connection.scalar(
                    sa.select(table.c.status).where(table.c.binding_id == "race-group")
                )
                == "active"
            )
    finally:
        release.set()
        pending = [task for task in (creating, deletion) if task is not None]
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_competing_owner_transfers_leave_exactly_one_owner(mysql):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from testing_agent.core.errors import AppError
    from testing_agent.models.project import Project
    from testing_agent.models.project_member import ProjectMember
    from testing_agent.models.user import User
    from testing_agent.repositories.project import ProjectRepository
    from testing_agent.services.project import ProjectService

    suffix = uuid4().hex
    pid, owner, a, b = (f"{key}-{suffix}" for key in ("project", "owner", "a", "b"))
    with mysql.begin() as connection:
        connection.execute(
            sa.insert(User), [dict(user_id=uid, nickname=uid) for uid in (owner, a, b)]
        )
        connection.execute(sa.insert(Project), dict(project_id=pid, user_id=owner, name=pid))
        connection.execute(
            sa.insert(ProjectMember),
            [dict(project_id=pid, user_id=uid, role="member") for uid in (a, b)],
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def transfer(target):
        async with sessions() as session:
            try:
                await ProjectService(ProjectRepository(session)).transfer(owner, pid, target)
                return True
            except AppError:
                await session.rollback()
                return False

    try:
        assert sorted(await asyncio.gather(transfer(a), transfer(b))) == [False, True]
        async with sessions() as session:
            project_owner = await session.scalar(
                sa.select(Project.user_id).where(Project.project_id == pid)
            )
            members = set(
                (
                    await session.scalars(
                        sa.select(ProjectMember.user_id).where(ProjectMember.project_id == pid)
                    )
                ).all()
            )
            assert project_owner in {a, b}
            assert project_owner not in members
            assert members == {owner, a, b} - {project_owner}
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(ProjectMember).where(ProjectMember.project_id == pid))
            connection.execute(sa.delete(Project).where(Project.project_id == pid))
            connection.execute(sa.delete(User).where(User.user_id.in_((owner, a, b))))


def test_mysql_member_unique_per_project_and_bindings_unique_per_instance(mysql):
    members = Base.metadata.tables["project_members"]
    bindings = Base.metadata.tables["resource_bindings"]
    with mysql.connect() as connection:
        member = seed_row(connection, members, {"role": "member"})
        with pytest.raises(IntegrityError):
            seed_row(
                connection,
                members,
                {
                    "project_id": member["project_id"],
                    "user_id": member["user_id"],
                    "role": "viewer",
                },
            )
        seed_row(connection, members, {"user_id": member["user_id"], "role": "viewer"})
        key = {
            "provider": "gitlab",
            "local_resource_type": "project",
            "local_resource_id": "same-project",
            "remote_resource_type": "group",
            "remote_resource_id": "9",
            "instance_key": "first",
        }
        seed_row(connection, bindings, key)
        with pytest.raises(IntegrityError):
            seed_row(connection, bindings, key)
        seed_row(connection, bindings, {**key, "instance_key": "second"})
        connection.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suite_name,case_name,key,case_values",
    [
        ("FunctionTestSuite", "FunctionTestCase", "suite_id", {"title": "case"}),
        ("UiTestSuite", "UiTestCase", "suite_id", {"name": "case", "steps_json": []}),
        (
            "ApiCollection",
            "ApiCase",
            "collection_id",
            {"name": "case", "method": "GET", "url_template": "/"},
        ),
    ],
)
async def test_mysql_hard_delete_waits_for_child_and_rechecks(
    mysql, suite_name, case_name, key, case_values
):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from testing_agent import models as models
    from testing_agent.core.errors import AppError
    from testing_agent.repositories.deletion import delete_resource

    suite_model, case_model = getattr(models, suite_name), getattr(models, case_name)
    with mysql.begin() as connection:
        parent = seed_row(connection, suite_model.__table__)
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    inserted, release = asyncio.Event(), asyncio.Event()

    async def create_child():
        async with sessions() as session:
            session.add(case_model(case_id=uuid4().hex, **{key: parent[key]}, **case_values))
            await session.flush()
            inserted.set()
            await release.wait()
            await session.commit()

    async def remove_parent(session, obj):
        with pytest.raises(AppError) as blocked:
            await delete_resource(session, obj)
        assert blocked.value.http_code == 409
        assert blocked.value.data["blockers"][0]["count"] == 1
        await session.rollback()

    creating = deleting = None
    try:
        async with sessions() as session:
            # Establish a REPEATABLE READ snapshot before the new child exists.
            obj = await session.scalar(
                sa.select(suite_model).where(getattr(suite_model, key) == parent[key])
            )
            creating = asyncio.create_task(create_child())
            await asyncio.wait_for(inserted.wait(), timeout=5)
            deleting = asyncio.create_task(remove_parent(session, obj))
            await asyncio.sleep(0.1)
            assert not deleting.done(), "parent deletion must wait for the child's FK lock"
            release.set()
            await asyncio.wait_for(asyncio.gather(creating, deleting), timeout=10)
    finally:
        release.set()
        tasks = [task for task in (creating, deleting) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()
