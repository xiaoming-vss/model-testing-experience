"""Environment kinds stay separate, and API runs refuse UI environments."""

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from authorization_database import AuthorizationDatabase
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from support.mysql_initialization import mysql as mysql
from support.mysql_initialization import seed_row

from testing_agent.core.errors import AppError, ErrApiEnvironmentKindMismatch
from testing_agent.models import Base
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.project import Project
from testing_agent.repositories.api_environment import ApiEnvironmentRepository
from testing_agent.schemas.api_run import RunApiCaseRequest, RunApiCollectionRequest
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService


class FakeEnvironmentRepository:
    session = AuthorizationDatabase(environment=True)

    def __init__(self, kind: str):
        self.rows: list[object] = []
        self.environment = SimpleNamespace(
            environment_id="env-1",
            project_id="project-1",
            kind=kind,
            base_url="https://api.example.test",
        )
        self.api_case = SimpleNamespace(
            case_id="case-1",
            collection_id="collection-1",
            method="GET",
            url_template="/ping",
            headers_json={},
            query_json={},
            body_type="none",
            body_json=None,
            body_text="",
            timeout_ms=1000,
        )
        self.collection = SimpleNamespace(
            collection_id="collection-1",
            requirement_id="requirement-1",
        )
        self.requirement = SimpleNamespace(requirement_id="requirement-1", sprint_id="sprint-1")
        self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
        self.project = SimpleNamespace(project_id="project-1", user_id="user-1")

    async def get_case(self, case_id):
        return self.api_case

    async def get_collection(self, collection_id):
        return self.collection

    async def get_requirement(self, requirement_id):
        return self.requirement

    async def get_sprint(self, sprint_id):
        return self.sprint

    async def get_project(self, project_id):
        return self.project

    async def get_environment(self, environment_id):
        return self.environment

    async def list_cases(self, collection_id):
        return [self.api_case]

    def add_all(self, rows):
        self.rows.extend(rows)

    async def commit(self):
        return None

    async def refresh(self, row):
        return None


@pytest.mark.asyncio
async def test_repository_lists_only_requested_kind():
    database = AuthorizationDatabase(environment=True)
    database.sync.add(
        ApiEnvironment(
            environment_id="env-ui",
            project_id="project-1",
            kind="ui",
            name="fixture-ui",
            base_url="https://web.example.test",
        )
    )
    database.sync.commit()

    repository = ApiEnvironmentRepository(database)

    api_rows = await repository.list_by_project("project-1", "api")
    ui_rows = await repository.list_by_project("project-1", "ui")

    assert [row.environment_id for row in api_rows] == ["env-1"]
    assert [row.environment_id for row in ui_rows] == ["env-ui"]


@pytest.mark.asyncio
async def test_api_case_run_rejects_ui_environment():
    service = ApiCaseService(FakeEnvironmentRepository(kind="ui"))

    with pytest.raises(AppError) as excinfo:
        await service.run("user-1", "case-1", RunApiCaseRequest(environmentId="env-1"))

    assert excinfo.value.code == ErrApiEnvironmentKindMismatch.code


@pytest.mark.asyncio
async def test_api_collection_run_rejects_ui_environment():
    service = ApiCollectionRunService(FakeEnvironmentRepository(kind="ui"))

    with pytest.raises(AppError) as excinfo:
        await service.run("user-1", "collection-1", RunApiCollectionRequest(environmentId="env-1"))

    assert excinfo.value.code == ErrApiEnvironmentKindMismatch.code


def test_environment_name_unique_within_kind():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Project(project_id="p", user_id="u", name="p"))
        session.add_all(
            [
                ApiEnvironment(environment_id="api", project_id="p", kind="api", name="dev"),
                ApiEnvironment(environment_id="ui", project_id="p", kind="ui", name="dev"),
            ]
        )
        session.commit()
        session.add(ApiEnvironment(environment_id="dup", project_id="p", kind="api", name="dev"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    engine.dispose()


def test_variable_keys_are_case_sensitive_in_mysql(mysql):
    table = ApiEnvironmentVar.__table__
    with mysql.connect() as connection:
        environment = seed_row(connection, ApiEnvironment.__table__, {"kind": "ui"})
        environment_id = environment["environment_id"]
        connection.execute(
            table.insert().values(
                env_var_id="var-lower",
                environment_id=environment_id,
                var_key="token",
                value="lower",
            )
        )
        connection.execute(
            table.insert().values(
                env_var_id="var-upper",
                environment_id=environment_id,
                var_key="Token",
                value="upper",
            )
        )
        collation = connection.scalar(
            sa.text(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'api_environment_vars' "
                "AND COLUMN_NAME = 'var_key'"
            )
        )
        connection.commit()
    assert collation == "utf8mb4_bin"

    # 大小写同名变量会让降级按设计拒绝；先清理，模块级 teardown 才能回退到 base。
    with mysql.connect() as connection:
        connection.execute(table.delete().where(table.c.env_var_id.in_(["var-lower", "var-upper"])))
        connection.commit()
