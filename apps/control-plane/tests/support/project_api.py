"""Shared project api fixtures and helpers; no collected tests."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from testing_agent.app import create_app
from testing_agent.db.session import get_session
from testing_agent.models import Base


@compiles(LONGTEXT, "sqlite")
def sqlite_longtext(type_, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def initialize():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            from testing_agent.models.auth_runtime import AuthRuntime

            await connection.execute(
                AuthRuntime.__table__.insert().values(
                    id=1,
                    mode="local",
                    fingerprint="",
                    generation=0,
                    reconcile_owner="",
                )
            )

    async def session():
        async with sessions() as value:
            yield value

    asyncio.run(initialize())
    from functools import partial

    from testing_agent.services import worker_lease_monitor

    monkeypatch.setattr(
        worker_lease_monitor, "sweep_once", partial(worker_lease_monitor.sweep_once, sessions)
    )
    app = create_app()
    app.state.test_sessions = sessions
    app.dependency_overrides[get_session] = session
    with TestClient(app) as client:
        yield client
    asyncio.run(engine.dispose())


def account(api, name):
    response = api.post(
        "/v1/register",
        json={"name": name, "password": "test-password", "email": f"{name}@example.test"},
    )
    assert response.status_code == 200, response.text
    user = response.json()["data"]
    response = api.post("/v1/login", json={"name": name, "password": "test-password"})
    assert response.status_code == 200, response.text
    return user, {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


def project(api, headers, name="shared"):
    response = api.post("/v1/projects", headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["data"]["projectId"]


def requirement(api, headers, pid):
    response = api.post(
        f"/v1/projects/{pid}/sprints",
        headers=headers,
        json={
            "name": "iteration",
            "startTime": "2026-09-01T00:00:00Z",
            "endTime": "2026-10-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    sid = response.json()["data"]["sprintId"]
    response = api.post(f"/v1/sprints/{sid}/requirements", headers=headers, json={"name": "req"})
    assert response.status_code == 200, response.text
    return response.json()["data"]["requirementId"]


def seed_requirement_source(api, requirement_id):
    """Authorization tests need an original file reference; they do not download it."""
    from sqlalchemy import select

    from testing_agent.models.requirement import Requirement

    async def provide_source_reference():
        async with api.app.state.test_sessions() as session:
            document = await session.scalar(
                select(Requirement).where(Requirement.requirement_id == requirement_id)
            )
            document.document_file_id = "source-file-for-authorization-test"
            await session.commit()

    asyncio.run(provide_source_reference())


@pytest.fixture
def gitlab_remote(monkeypatch):
    from testing_agent.services.gitlab_auth import GitLabAuthProvider
    from testing_agent.services.gitlab_resource import GitLabResourceClient

    calls = []

    async def validate(self, base_url, access_token):
        calls.append(("auth", base_url, access_token))

    async def group(self, base_url, token, group_id):
        calls.append(("group", base_url, token))
        return {"id": 7, "name": "group"}

    async def groups(self, base_url, token, **kwargs):
        calls.append(("groups", base_url, token))
        return {"items": [{"id": 7, "name": "group"}], "total": 1}

    monkeypatch.setattr(GitLabAuthProvider, "validate", validate)
    monkeypatch.setattr(GitLabResourceClient, "get_group", group)
    monkeypatch.setattr(GitLabResourceClient, "list_groups", groups)
    return calls


def gitlab_connection(api, headers, pid, name, url="https://gitlab.example"):
    response = api.post(
        f"/v1/projects/{pid}/integrations/gitlab/connections",
        headers=headers,
        json={"name": name, "baseUrl": url, "accessToken": name + "-token"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["connectionId"]
