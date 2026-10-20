"""Shared preparation for bug zentao attachments tests; no collected cases."""

import asyncio
import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from integration_test_driver import dispatch_sync, enable
from sqlalchemy import select

from support.bug_zentao_push_api import setup as setup
from support.project_api import api as api
from testing_agent.core.config import get_settings
from testing_agent.models.bug import Bug
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.stored_file import StoredFileService


@pytest.fixture(autouse=True)
def migration_mode(api):
    enable(api)


CONTENT = b"attachment contents\n"


HASH = hashlib.sha256(CONTENT).hexdigest()


@pytest.fixture
def attachments(api, setup, monkeypatch):
    s = setup
    original = s["remote"].handle
    s.update(
        uploads=[],
        lookup=[],
        attachment_failure="",
        upload_entered=threading.Event(),
        upload_release=threading.Event(),
        upload_block=False,
        lookup_hash=HASH,
    )

    async def handle(request):
        body = json.loads(request.content)
        params = body.get("params", {})
        name = params.get("name")
        if name not in {"upload_bug_attachment", "get_bug_attachment"}:
            result = await original(request)
            if name == "get_bugs_bugID" and s.get("on_attachment_verify"):
                await s["on_attachment_verify"]()
            return result
        args = params["arguments"]
        s["remote"].headers.append(request.headers.get("token"))
        if name == "upload_bug_attachment":
            s["uploads"].append(args)
            s["upload_entered"].set()
            while s["upload_block"] and not s["upload_release"].is_set():
                await asyncio.sleep(0.01)
            if s["attachment_failure"] == "timeout":
                raise httpx.ReadTimeout("signed-url-secret-and-token", request=request)
            data = {"status": "success", "id": 100 + len(s["uploads"])}
            if s["attachment_failure"] == "known":
                data = {"status": "fail", "uncertain": False, "errorCode": "SOURCE_FETCH"}
            if s["attachment_failure"] == "missing-id":
                data = {"status": "success"}
        else:
            s["lookup"].append(args)
            data = {
                "status": "success",
                "id": args["fileId"],
                "filename": "附件.txt",
                "size": len(CONTENT),
                "sha256": s["lookup_hash"],
            }
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"structuredContent": data}}
        )

    s["remote"].handle = handle

    async def ticket(self, row):
        return {
            "url": f"http://s3.test/bucket/{row.file_id}?signature=secret",
            "size": row.size,
            "sha256": row.sha256,
            "filename": row.filename,
        }

    monkeypatch.setattr(StoredFileService, "ticket", ticket)
    return s


def seed(api, s, file_id="attachment-1", *, status="attached", purpose="attachment"):
    async def insert():
        async with api.app.state.test_sessions() as session:
            bug = await session.scalar(select(Bug).where(Bug.bug_id == s["bug"]["bugId"]))
            session.add(
                StoredFile(
                    file_id=file_id,
                    project_id=s["pid"],
                    uploaded_by=bug.reporter_user_id,
                    filename="附件.txt",
                    content_type="text/plain",
                    size=len(CONTENT),
                    sha256=HASH,
                    bucket=get_settings().s3.bucket,
                    object_key=f"objects/{file_id}",
                    staging_key=f"staging/{file_id}",
                    status=status,
                    purpose=purpose,
                    resource_type="bug",
                    resource_id=bug.bug_id,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            await session.commit()

    asyncio.run(insert())
    return file_id


def rows(api):
    async def read():
        async with api.app.state.test_sessions() as session:
            return [
                {
                    "file": r.file_id,
                    "status": r.status,
                    "remote": r.remote_file_id,
                    "operation": r.operation_id,
                }
                for r in await session.scalars(
                    select(BugZentaoAttachment).order_by(BugZentaoAttachment.id)
                )
            ]

    return asyncio.run(read())


def push(api, s):
    response = dispatch_sync(api, s, headers=s["owner"])
    assert response.status_code == 200, response.text
    assert "signature=secret" not in response.text
    assert "signed-url-secret-and-token" not in response.text
    return response.json()["data"]
