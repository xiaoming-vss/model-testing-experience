"""Shared preparation for stored files tests; no collected cases."""

import hashlib
from datetime import timedelta

import pytest_asyncio
from moto import mock_aws
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from testing_agent.core.object_storage import ObjectStorage, ObjectStorageSettings
from testing_agent.models import Base
from testing_agent.models.bug import Bug
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.user import User
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.stored_file import StoredFileService, utcnow


@compiles(LONGTEXT, "sqlite")
def longtext_sqlite(type_, compiler, **kwargs):
    return "TEXT"


@pytest_asyncio.fixture
async def files():
    with mock_aws():
        settings = ObjectStorageSettings(
            enabled=True, bucket="mtx-test", access_key="test", secret_key="test"
        )
        storage = ObjectStorage(settings)
        storage.client.create_bucket(Bucket=settings.bucket)
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add_all(
                [
                    User(user_id="owner", nickname="owner"),
                    User(user_id="viewer", nickname="viewer"),
                    User(user_id="member", nickname="member"),
                    Project(project_id="p", user_id="owner", name="p"),
                    Project(project_id="q", user_id="owner", name="q"),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    ProjectMember(project_id="p", user_id="viewer", role="viewer"),
                    ProjectMember(project_id="p", user_id="member", role="member"),
                    Sprint(
                        sprint_id="s",
                        project_id="p",
                        name="s",
                        start_time=utcnow(),
                        end_time=utcnow() + timedelta(days=1),
                    ),
                    Requirement(requirement_id="r", sprint_id="s", name="existing"),
                    Bug(bug_id="bug-1", project_id="p", bug_no=2, title="bug", found_sprint_id="s"),
                ]
            )
            await session.commit()
            yield StoredFileService(session, settings, storage)
        await engine.dispose()


async def upload(files, content=b"hello", filename="a.txt", purpose="requirement"):
    ticket = await files.initiate(
        "owner",
        FileUploadRequest(
            project_id="p",
            filename=filename,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            purpose=purpose,
        ),
    )
    row = await files.get(ticket["fileId"])
    files.storage.client.put_object(Bucket=row.bucket, Key=row.staging_key, Body=content)
    return row, ticket
