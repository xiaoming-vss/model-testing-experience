"""Real authorization tables for older in-memory business-repository fixtures.

These fixtures still fake business rows; authorization uses the production SQL and
Casbin policy. Cross-user HTTP behavior is covered by test_project_membership_api.
"""

from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from testing_agent.models import Base
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.user import User


@compiles(LONGTEXT, "sqlite")
def longtext_sqlite(type_, compiler, **kwargs):
    return "TEXT"


class AuthorizationDatabase:
    def __init__(self, *, environment=False):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.sync = Session(self.engine, expire_on_commit=False)
        self.sync.add_all(
            [
                User(user_id="user-1", nickname="fixture-owner"),
                Project(project_id="project-1", user_id="user-1", name="fixture"),
            ]
        )
        self.sync.add(
            IntegrationConnection(
                connection_id="llm-1",
                user_id="user-1",
                provider="llm",
                name="fixture-llm",
                project_id="project-1",
                status="active",
                secret_json={"apiKey": "fixture-only"},
            )
        )
        self.sync.add(
            IntegrationConnection(
                connection_id="connection-1",
                user_id="user-1",
                provider="llm",
                name="fixture-llm-other",
                project_id="project-1",
                status="active",
                secret_json={"apiKey": "fixture-only"},
            )
        )
        self.sync.add(
            IntegrationConnection(
                connection_id="conn-1",
                user_id="user-1",
                provider="llm",
                name="fixture-llm-legacy",
                project_id="project-1",
                status="active",
                secret_json={"apiKey": "fixture-only"},
            )
        )
        if environment:
            from testing_agent.models.api_environment import ApiEnvironment
            from testing_agent.models.api_environment_var import ApiEnvironmentVar

            self.sync.add(
                ApiEnvironment(
                    environment_id="env-1",
                    project_id="project-1",
                    name="fixture-env",
                    base_url="https://api.example.test",
                )
            )
            self.sync.add(
                ApiEnvironmentVar(
                    env_var_id="fixture-var",
                    environment_id="env-1",
                    var_key="token",
                    value="abc",
                    is_secret=False,
                )
            )
        self.sync.commit()

    async def scalar(self, stmt):
        return self.sync.scalar(stmt)

    async def scalars(self, stmt):
        return self.sync.scalars(stmt)

    async def execute(self, stmt):
        return self.sync.execute(stmt)

    async def run_sync(self, fn):
        return fn(self.sync)

    async def commit(self):
        self.sync.commit()


class AuthorizedRepositoryFixture:
    session = AuthorizationDatabase()

    async def get_project(self, project_id):
        from sqlalchemy import select

        return await self.session.scalar(select(Project).where(Project.project_id == project_id))
