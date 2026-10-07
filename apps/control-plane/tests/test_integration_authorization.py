import pytest
import pytest_asyncio
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_initial_schema_migration import compile_longtext_for_sqlite  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models import Base
from testing_agent.models.bug import Bug
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.integration_job import IntegrationJob
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.models.user import User
from testing_agent.services.integration_authorization import IntegrationAuthorization
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


async def test_access_uses_only_the_job_actors_connection_and_masks_repr(db):
    sessions, cipher = db
    async with sessions() as session:
        authorization = IntegrationAuthorization(session, cipher)
        own = await authorization.access(job())
        assert own.token.get_secret_value() == "member-secret"
        assert "member-secret" not in repr(own)
        assert (await authorization.access(job("owner"))).token.get_secret_value() == "owner-secret"
        mismatched = job()
        mismatched.connection_id = "owner-connection"
        with pytest.raises(AppError):
            await authorization.access(mismatched)


@pytest.mark.parametrize("role", ["viewer", "developer"])
async def test_role_downgrade_denies_new_access_even_if_bug_remains_readable(db, role):
    sessions, cipher = db
    async with sessions() as session:
        await session.execute(
            update(ProjectMember).where(ProjectMember.user_id == "member").values(role=role)
        )
        await session.commit()
        with pytest.raises(AppError) as error:
            await IntegrationAuthorization(session, cipher).access(job())
        assert error.value.http_code == 403


@pytest.mark.parametrize(
    "change", ["membership", "user", "bug", "service", "authorization", "connection"]
)
async def test_removal_and_revocation_deny_job_access(db, change):
    sessions, cipher = db
    async with sessions() as session:
        commands = {
            "membership": delete(ProjectMember).where(ProjectMember.user_id == "member"),
            "user": delete(User).where(User.user_id == "member"),
            "bug": delete(Bug).where(Bug.bug_id == "b"),
            "service": delete(SharedService).where(SharedService.service_id == "svc"),
            "authorization": delete(ServiceAuthorization).where(
                ServiceAuthorization.user_id == "member"
            ),
            "connection": update(IntegrationConnection)
            .where(IntegrationConnection.user_id == "member")
            .values(status="invalid"),
        }
        await session.execute(commands[change])
        await session.commit()
        with pytest.raises(AppError) as error:
            await IntegrationAuthorization(session, cipher).access(job())
        assert error.value.http_code in (403, 404)


async def test_access_revision_changes_on_endpoint_and_credential_replacement(db):
    sessions, cipher = db
    async with sessions() as session:
        authorization = IntegrationAuthorization(session, cipher)
        first = await authorization.access(job())
        await session.execute(update(SharedService).values(base_url="http://other.test/mcp"))
        await session.commit()
        second = await authorization.access(job())
        assert first.access_revision != second.access_revision
        assert second.endpoint == "http://other.test/mcp"
        await session.execute(
            update(IntegrationConnection)
            .where(IntegrationConnection.user_id == "member")
            .values(secret_json={"token": cipher.encrypt("changed-secret")})
        )
        await session.commit()
        third = await authorization.access(job())
        assert second.access_revision != third.access_revision
        assert third.token.get_secret_value() == "changed-secret"
