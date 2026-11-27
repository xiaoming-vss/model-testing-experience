"""Shared project api fixtures and helpers; no collected tests."""

import asyncio

import bcrypt
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
    # Hashing at the default bcrypt cost dominates account setup, and no API test depends on it.
    gensalt = bcrypt.gensalt
    monkeypatch.setattr(bcrypt, "gensalt", lambda **options: gensalt(rounds=4, **options))
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
    """Seed a verified document and isolated object storage for authorization tests."""
    from datetime import UTC, datetime, timedelta
    from hashlib import sha256
    from types import SimpleNamespace
    from uuid import uuid4

    from sqlalchemy import select

    from support.memory_storage import Storage
    from testing_agent.api.deps_common import get_file_service
    from testing_agent.models.project import Project
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.sprint import Sprint
    from testing_agent.models.stored_file import StoredFile

    content = b"isolated requirement source"
    file_id = str(uuid4())
    objects = getattr(api.app.state, "test_requirement_objects", None)
    if objects is None:
        objects = {}
        api.app.state.test_requirement_objects = objects
    objects[file_id] = content

    api.app.dependency_overrides[get_file_service] = lambda: SimpleNamespace(
        settings=SimpleNamespace(bucket="test-bucket"), storage=Storage(objects=objects)
    )

    async def provide_source_reference():
        async with api.app.state.test_sessions() as session:
            document = await session.scalar(
                select(Requirement).where(Requirement.requirement_id == requirement_id)
            )
            project = await session.scalar(
                select(Project)
                .join(Sprint, Sprint.project_id == Project.project_id)
                .where(Sprint.sprint_id == document.sprint_id)
            )
            document.document_type = "docx"
            document.document_file_id = file_id
            document.document_filename = "requirement.docx"
            document.document_hash = sha256(content).hexdigest()
            session.add(
                StoredFile(
                    file_id=file_id,
                    project_id=project.project_id,
                    uploaded_by=project.user_id,
                    filename="requirement.docx",
                    content_type="application/octet-stream",
                    size=len(content),
                    sha256=document.document_hash,
                    bucket="test-bucket",
                    object_key=file_id,
                    staging_key="",
                    status="attached",
                    purpose="requirement",
                    resource_type="requirement",
                    resource_id=requirement_id,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            await session.commit()

    asyncio.run(provide_source_reference())


@pytest.fixture
def gitlab_remote(monkeypatch):
    from testing_agent.services.gitlab_auth import GitLabAuthProvider
    from testing_agent.services.gitlab_resource import GitLabResourceClient

    calls = []

    async def validate(self, base_url, access_token, **kwargs):
        calls.append(("auth", base_url, access_token))

    async def groups(self, base_url, token, **kwargs):
        calls.append(("groups", base_url, token))
        return {"items": [{"id": 7, "name": "group"}], "total": 1}

    monkeypatch.setattr(GitLabAuthProvider, "validate", validate)
    monkeypatch.setattr(GitLabResourceClient, "list_groups", groups)
    return calls


def _seed_connection(api, headers, **fields):
    """Insert an owned connection; scenario setup must not depend on a public route."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from testing_agent.core.config import get_settings
    from testing_agent.models.integration_connection import IntegrationConnection
    from testing_agent.services.integration_credentials import IntegrationCredentialCipher

    profile = api.get("/v1/user", headers=headers)
    assert profile.status_code == 200, profile.text
    cipher = IntegrationCredentialCipher(get_settings().integration_key)
    provider = fields["provider"]
    connection_id = f"{provider}-{uuid4().hex}"
    connection = IntegrationConnection(
        connection_id=connection_id,
        user_id=profile.json()["data"]["userId"],
        status="active",
        last_auth_at=datetime.now(UTC),
        last_auth_error="",
        account="",
        **{
            **fields,
            "access_token": cipher.encrypt(fields["access_token"])
            if fields["access_token"]
            else "",
            "secret_json": {
                key: cipher.encrypt(value) for key, value in fields["secret_json"].items()
            },
        },
    )

    async def insert():
        async with api.app.state.test_sessions() as session:
            session.add(connection)
            await session.commit()

    asyncio.run(insert())
    return connection_id


def seed_llm_connection(
    api,
    headers,
    *,
    project_id="",
    name="llm",
    base_url="https://llm.example/v1",
    api_key="fixture-secret",
    model_id="model",
):
    return _seed_connection(
        api,
        headers,
        provider="llm",
        project_id=project_id,
        name=name,
        base_url=base_url,
        auth_type="api_key",
        secret_json={"apiKey": api_key},
        access_token="",
        extra_json={"modelId": model_id},
    )


def delete_connection(api, connection_id):
    """Remove a seeded connection without going through a removed HTTP route."""
    from sqlalchemy import delete

    from testing_agent.models.integration_connection import IntegrationConnection

    async def remove():
        async with api.app.state.test_sessions() as session:
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.connection_id == connection_id
                )
            )
            await session.commit()

    asyncio.run(remove())


def gitlab_connection(api, headers, pid, name, url="https://gitlab.example"):
    return _seed_connection(
        api,
        headers,
        provider="gitlab",
        project_id=pid,
        name=name,
        base_url=url,
        auth_type="personal_access_token",
        secret_json={},
        access_token=name + "-token",
        extra_json={"allowHttp": False, "insecureSkipVerify": False},
    )
