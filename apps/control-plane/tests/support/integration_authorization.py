"""Shared preparation for integration authorization tests; no collected cases."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from support.initial_schema_migration import compile_longtext_for_sqlite  # noqa: F401
from testing_agent.models import Base
from testing_agent.models.bug import Bug
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.integration_job import IntegrationJob
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.models.user import User
from testing_agent.services.integration_credentials import IntegrationCredentialCipher


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    tables = [
        model.__table__
        for model in (
            User,
            Project,
            ProjectMember,
            Bug,
            SharedService,
            IntegrationConnection,
            ServiceAuthorization,
        )
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cipher = IntegrationCredentialCipher("integration-auth-isolated-test")
    async with sessions() as session:
        session.add_all(
            [User(user_id="owner", nickname="owner"), User(user_id="member", nickname="member")]
        )
        session.add(Project(project_id="p", user_id="owner", name="p"))
        await session.flush()
        session.add(ProjectMember(project_id="p", user_id="member", role="member"))
        session.add(Bug(bug_id="b", project_id="p", title="b", found_sprint_id="s"))
        session.add(
            SharedService(
                service_id="svc",
                project_id="p",
                provider="mcp",
                template_id="zentao",
                name="mcp",
                base_url="http://mcp.test/mcp",
            )
        )
        session.add_all(
            [
                IntegrationConnection(
                    connection_id=actor + "-connection",
                    user_id=actor,
                    project_id="p",
                    provider="mcp",
                    name=actor,
                    secret_json={"token": cipher.encrypt(actor + "-secret")},
                )
                for actor in ("owner", "member")
            ]
        )
        await session.flush()
        session.add_all(
            [
                ServiceAuthorization(
                    service_id="svc", user_id=actor, connection_id=actor + "-connection"
                )
                for actor in ("owner", "member")
            ]
        )
        await session.commit()
    yield sessions, cipher
    await engine.dispose()


def job(actor="member", **overrides):
    return IntegrationJob(
        actor_user_id=actor,
        connection_id=actor + "-connection",
        project_id="p",
        service_id="svc",
        bug_id="b",
        **overrides,
    )
