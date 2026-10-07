"""Disposable CP process for protocol acceptance; run exclusively with the CP test interpreter."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn
from sqlalchemy import event
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from testing_agent.app import create_app
from testing_agent.core.config import Settings, get_settings
from testing_agent.core.security import create_access_token
from testing_agent.db.session import get_session
from testing_agent.models import Base
from testing_agent.models.bug import Bug
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.models.sprint import Sprint
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.user import User
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.service_instance import instance_key
from testing_agent.services.stored_file import StoredFileService

CONTENT = b"isolated-image"
INSTANCE = "http://zentao.fixture/sub"


@compiles(LONGTEXT, "sqlite")
def longtext(type_, compiler, **kwargs):
    return "TEXT"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--mcp", required=True)
    parser.add_argument("--info", required=True)
    parser.add_argument("--lost-result", action="store_true")
    parser.add_argument("--lost-prepare", action="store_true")
    parser.add_argument("--offline-results", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_mapping(
        {
            "security": {
                "jwt": {"key": "disposable-jwt-key-for-http-fixture-only"},
                "integration": {"key": "disposable-cipher-key"},
                "worker": {"key": "old-worker-key"},
                "integration_worker": {"key": "integration-fixture-key"},
            },
            "data": {"db": {"user": {"dsn": "sqlite+aiosqlite:///" + args.db}}},
            "storage": {"s3": {"bucket": "isolated"}},
            "integration_execution": {
                "enabled": True,
                "all_projects": True,
                "runtime_generation": "fixture-epoch",
                "lease_seconds": 10,
            },
        }
    )
    # SQLite cannot reproduce MySQL row locks. Serialize this fixture's local transactions;
    # real cross-replica SKIP LOCKED coverage belongs to the separate MySQL acceptance tests.
    engine = create_async_engine(settings.database_url, pool_size=1, max_overflow=0)

    @event.listens_for(engine.sync_engine, "connect")
    def transactions(connection, _):
        connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cipher = IntegrationCredentialCipher(settings.integration_key)

    async def seed():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            now = datetime.now(UTC)
            session.add(User(user_id="actor", nickname="isolated-owner"))
            session.add(Project(project_id="project", user_id="actor", name="isolated"))
            await session.flush()
            session.add(
                Sprint(
                    sprint_id="sprint",
                    project_id="project",
                    name="sprint",
                    start_time=now,
                    end_time=now + timedelta(days=1),
                )
            )
            await session.flush()
            session.add(Requirement(requirement_id="requirement", sprint_id="sprint", name="req"))
            session.add(
                Bug(
                    bug_id="bug",
                    project_id="project",
                    bug_no=1,
                    title="isolated Bug",
                    description_html='<p>evidence<img data-file-id="image"></p>',
                    found_sprint_id="sprint",
                    requirement_id="requirement",
                    reporter_user_id="actor",
                )
            )
            session.add(
                SharedService(
                    service_id="service",
                    project_id="project",
                    provider="mcp",
                    template_id="zentao",
                    name="fixture",
                    base_url=args.mcp,
                    zentao_instance_url=INSTANCE,
                )
            )
            session.add(
                IntegrationConnection(
                    connection_id="connection",
                    project_id="project",
                    user_id="actor",
                    provider="mcp",
                    name="fixture",
                    secret_json={"token": cipher.encrypt("actor-secret")},
                )
            )
            await session.flush()
            session.add(
                ServiceAuthorization(
                    service_id="service", user_id="actor", connection_id="connection"
                )
            )
            for kind, local, remote, number, parent in (
                ("project", "project", "project", "10", ""),
                ("sprint", "sprint", "execution", "20", "10"),
                ("requirement", "requirement", "story", "30", "20"),
            ):
                session.add(
                    ResourceBinding(
                        binding_id="binding-" + kind,
                        user_id="actor",
                        provider="zentao",
                        instance_url=INSTANCE,
                        instance_key=instance_key(INSTANCE),
                        connection_id="connection",
                        local_resource_type=kind,
                        local_resource_id=local,
                        remote_resource_type=remote,
                        remote_resource_id=number,
                        remote_parent_id=parent,
                        extra_json={"mcpServiceId": "service"},
                    )
                )
            session.add(
                StoredFile(
                    file_id="image",
                    project_id="project",
                    uploaded_by="actor",
                    filename="image.png",
                    content_type="image/png",
                    size=len(CONTENT),
                    sha256=hashlib.sha256(CONTENT).hexdigest(),
                    bucket="isolated",
                    object_key="image",
                    staging_key="staging/image",
                    status="attached",
                    purpose="attachment",
                    resource_type="bug",
                    resource_id="bug",
                    expires_at=now + timedelta(days=1),
                )
            )
            await session.commit()

    asyncio.run(seed())
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    async def session():
        async with sessions() as value:
            yield value

    app.dependency_overrides[get_session] = session
    from functools import partial

    from testing_agent.services import worker_lease_monitor

    worker_lease_monitor.sweep_once = partial(worker_lease_monitor.sweep_once, sessions)

    async def ticket(self, row):
        return {
            "url": args.mcp.removesuffix("/mcp") + "/source?X-Amz-Signature=fixture-signature",
            "expiresIn": 900,
        }

    StoredFileService.ticket = ticket
    lost = set()

    @app.middleware("http")
    async def lost_ack(request, call_next):
        if (
            args.offline_results
            and request.url.path.endswith(("/result", "/evidence"))
            and not (Path(args.info).parent / "resume-results").exists()
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse({"message": "isolated result outage"}, status_code=503)
        response = await call_next(request)
        suffix = "/result" if args.lost_result else "/prepare" if args.lost_prepare else ""
        if (
            suffix
            and request.url.path.endswith(suffix)
            and suffix not in lost
            and response.status_code == 200
        ):
            from fastapi.responses import JSONResponse

            lost.add(suffix)
            return JSONResponse({"message": "isolated response loss"}, status_code=503)
        return response

    Path(args.info).write_text(json.dumps({"token": create_access_token("actor", settings)}))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
