"""Exercise persistent attachment state through the real Bug HTTP/MCP integration."""

import asyncio
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from integration_test_driver import dispatch_sync, enable
from sqlalchemy import select
from test_bug_zentao_push_api import setup as setup
from test_project_membership_api import api as api

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


def test_creation_uploads_independent_files_once_and_supplements_later_files(api, attachments):
    s = attachments
    seed(api, s)
    data = push(api, s)
    assert data["status"] == "succeeded" and data["attachmentStatus"] == "succeeded"
    assert s["uploads"] == [
        {
            "bugId": 50,
            "filename": "附件.txt",
            "size": len(CONTENT),
            "sha256": HASH,
            "contentType": "text/plain",
            "downloadUrl": "http://s3.test/bucket/attachment-1?signature=secret",
        }
    ]
    assert rows(api)[0]["remote"] == 101
    assert push(api, s)["attachmentStatus"] == "succeeded"
    assert len(s["uploads"]) == 1
    seed(api, s, "attachment-2")
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["attachmentStatus"] == "pending"
    assert push(api, s)["attachmentStatus"] == "succeeded"
    assert len(s["remote"].writes) == 1 and len(s["uploads"]) == 2
    assert set(s["remote"].headers) == {"owner-secret"}


def test_archived_and_inline_files_are_excluded(api, attachments):
    s = attachments
    seed(api, s, "archived", status="archived")
    seed(api, s, "inline", purpose="rich_text")
    assert push(api, s)["attachmentStatus"] == "none"
    assert s["uploads"] == []


def test_known_failure_retries_only_the_failed_file_without_recreating_bug(api, attachments):
    s = attachments
    seed(api, s)
    assert push(api, s)["attachmentStatus"] == "succeeded"
    seed(api, s, "later-file")
    s["attachment_failure"] = "known"
    data = push(api, s)
    assert data["status"] == "succeeded" and data["attachmentStatus"] == "failed"
    assert data["remoteBugId"] == 50 and "附件同步失败" in data["errorMessage"]
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["ready"] is True
    s["attachment_failure"] = ""
    assert push(api, s)["attachmentStatus"] == "succeeded"
    assert len(s["remote"].writes) == 1
    assert [x["downloadUrl"].split("?")[0] for x in s["uploads"]] == [
        "http://s3.test/bucket/attachment-1",
        "http://s3.test/bucket/later-file",
        "http://s3.test/bucket/later-file",
    ]


@pytest.mark.parametrize("failure", ["timeout", "missing-id"])
def test_uncertain_upload_blocks_repeat_and_reconciles_by_remote_content(api, attachments, failure):
    s = attachments
    fid = seed(api, s)
    s["attachment_failure"] = failure
    data = push(api, s)
    assert data["status"] == "succeeded" and data["attachmentStatus"] == "unknown"
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["ready"] is True
    assert push(api, s)["attachmentStatus"] == "unknown"
    assert len(s["uploads"]) == 1 and len(s["remote"].writes) == 1
    url = f"{s['url']}/attachments/{fid}/reconcile"
    s["lookup_hash"] = "0" * 64
    assert api.post(url, headers=s["owner"], json={"remoteFileId": 101}).status_code == 400
    s["lookup_hash"] = HASH
    restored = api.post(url, headers=s["owner"], json={"remoteFileId": 101})
    assert restored.status_code == 200, restored.text
    assert restored.json()["data"]["attachmentStatus"] == "succeeded"
    assert rows(api)[0]["remote"] == 101
    assert len(s["uploads"]) == 1


def test_parallel_attachment_retry_reserves_one_upload(api, attachments):
    s = attachments
    push(api, s)
    seed(api, s)
    s["upload_block"] = True
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(dispatch_sync, api, s, headers=s["owner"])
        assert s["upload_entered"].wait(timeout=10)
        try:
            second = pool.submit(dispatch_sync, api, s, headers=s["owner"])
            other = second.result(timeout=10)
            assert other.status_code == 409, other.text
        finally:
            s["upload_release"].set()
        assert first.result(timeout=10).json()["data"]["attachmentStatus"] == "succeeded"
    assert len(s["uploads"]) == 1 and len(s["remote"].writes) == 1


def test_supplement_requires_current_members_own_token_and_original_instance(api, attachments):
    from test_bug_zentao_push_api import INSTANCE
    from test_project_membership_api import account

    s = attachments
    push(api, s)
    seed(api, s)
    _, member = account(api, "attachment-member")
    _, viewer = account(api, "attachment-viewer")
    for name, role in [("attachment-member", "member"), ("attachment-viewer", "viewer")]:
        assert (
            api.post(
                f"/v1/projects/{s['pid']}/members",
                headers=s["owner"],
                json={"name": name, "role": role},
            ).status_code
            == 200
        )
    assert dispatch_sync(api, s, headers=viewer).status_code == 403
    denied = dispatch_sync(api, s, headers=member)
    assert denied.status_code == 403, denied.text
    assert s["uploads"] == []
    assert (
        api.put(
            f"{s['path']}/{s['sid']}/authorization",
            headers=member,
            json={"token": "member-attachment-token"},
        ).status_code
        == 200
    )
    s["remote"].instance = "http://different.test"
    assert (
        dispatch_sync(api, s, headers=member).json()["data"]["latestJob"]["jobStatus"] == "failed"
    )
    assert s["uploads"] == []
    s["remote"].instance = INSTANCE
    s["remote"].headers.clear()
    assert dispatch_sync(api, s, headers=member).json()["data"]["attachmentStatus"] == "succeeded"
    assert set(s["remote"].headers) == {"member-attachment-token"}
    assert len(s["remote"].writes) == 1


def test_crashed_preparation_can_resume_but_crashed_upload_stays_uncertain(api, attachments):
    from test_bug_zentao_push_api import change

    s = attachments
    fid = seed(api, s)
    s["attachment_failure"] = "known"
    assert push(api, s)["attachmentStatus"] == "failed"
    change(api, BugZentaoAttachment, "status", "pending", file_id=fid)
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["attachmentStatus"] == "syncing"
    change(
        api,
        BugZentaoAttachment,
        "updated_at",
        datetime.now(UTC) - timedelta(minutes=10),
        file_id=fid,
    )
    s["attachment_failure"] = ""
    assert push(api, s)["attachmentStatus"] == "succeeded"
    before = len(s["uploads"])
    change(api, BugZentaoAttachment, "status", "uploading", file_id=fid)
    change(
        api,
        BugZentaoAttachment,
        "updated_at",
        datetime.now(UTC) - timedelta(minutes=10),
        file_id=fid,
    )
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["attachmentStatus"] == "unknown"
    assert push(api, s)["attachmentStatus"] == "unknown"
    assert len(s["uploads"]) == before


def test_revoked_authorization_while_reading_remote_bug_prevents_attachment_write(api, attachments):
    from sqlalchemy import select

    from testing_agent.models.integration_connection import IntegrationConnection

    s = attachments
    push(api, s)
    seed(api, s)

    async def revoke():
        async with api.app.state.test_sessions() as session:
            from testing_agent.services.worker_authorization import revoke_executions

            for connection in await session.scalars(
                select(IntegrationConnection).where(IntegrationConnection.provider == "mcp")
            ):
                connection.status = "invalid"
                await revoke_executions(
                    session, actor=connection.user_id, connection_id=connection.connection_id
                )
            await session.commit()

    s["on_attachment_verify"] = revoke
    result = push(api, s)
    assert result["status"] == "succeeded" and result["latestJob"]["jobStatus"] == "canceled"
    assert s["uploads"] == [] and len(s["remote"].writes) == 1


def test_stale_pending_row_cannot_override_unknown_upload_ledger(api, attachments):
    from test_bug_zentao_push_api import change

    s = attachments
    fid = seed(api, s)
    s["attachment_failure"] = "timeout"
    assert push(api, s)["attachmentStatus"] == "unknown"
    assert len(s["uploads"]) == 1
    change(api, BugZentaoAttachment, "status", "pending", file_id=fid)
    change(
        api,
        BugZentaoAttachment,
        "updated_at",
        datetime.now(UTC) - timedelta(minutes=10),
        file_id=fid,
    )
    s["attachment_failure"] = ""
    result = push(api, s)
    assert result["latestJob"]["result"]["steps"]["upload_attachment:" + fid] == "blocked"
    assert len(s["uploads"]) == 1
