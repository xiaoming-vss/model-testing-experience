"""Inline images exercise the real Bug API, storage and MCP orchestration."""

import json

import httpx
import pytest
from integration_test_driver import dispatch_sync, enable
from test_bug_zentao_attachments import attachments as attachments
from test_bug_zentao_attachments import push, rows, seed
from test_bug_zentao_push_api import change
from test_bug_zentao_push_api import setup as setup
from test_project_membership_api import api as api

from testing_agent.models.bug import Bug
from testing_agent.models.stored_file import StoredFile


@pytest.fixture(autouse=True)
def migration_mode(api):
    enable(api)


@pytest.fixture
def inline(api, attachments):
    s = attachments
    original = s["remote"].handle
    s.update(steps="", description_writes=[], description_failure="")

    async def handle(request):
        body = json.loads(request.content)
        params = body.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "put_bugs_bugID":
            s["description_writes"].append(args)
            s["remote"].headers.append(request.headers.get("token"))
            if s["description_failure"] == "timeout":
                s["steps"] = args["payload"]["steps"]
                raise httpx.ReadTimeout("secret-ticket", request=request)
            s["steps"] = args["payload"]["steps"]
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"structuredContent": {"status": "success"}},
                },
            )
        result = await original(request)
        if name == "post_bugs":
            s["steps"] = args["payload"]["steps"]
        if name == "get_bugs_bugID":
            data = result.json()
            bug = data["result"]["structuredContent"]["bug"]
            bug["steps"] = s["steps"]
            bug["files"] = {
                str(100 + i): {
                    "id": 100 + i,
                    "objectType": "bug",
                    "objectID": 50,
                    "extension": "png",
                    "deleted": "0",
                    "url": f"/index.php?m=file&f=download&t=json&fileID={100 + i}",
                }
                for i, upload in enumerate(s["uploads"], 1)
            }
            return httpx.Response(200, json=data)
        return result

    s["remote"].handle = handle
    return s


def image(api, s, file_id="inline-image"):
    seed(api, s, file_id)
    change(api, StoredFile, "filename", "截图.png", file_id=file_id)
    change(api, StoredFile, "content_type", "image/png", file_id=file_id)
    html = f'<p>截图位置</p><p><img data-file-id="{file_id}"></p><p>后续说明</p>'
    change(api, Bug, "description_html", html, bug_id=s["bug"]["bugId"])
    return html


def test_inline_image_uploads_and_replaces_placeholder_without_recreating(api, inline):
    s = inline
    image(api, s)
    data = push(api, s)
    assert len(s["uploads"]) == 1, "正文中的图片没有进入实际 MCP 上传链路"
    assert data["descriptionStatus"] == "succeeded"
    assert (
        'src="http://zentao.test/index.php?m=file&amp;f=read&amp;t=png&amp;fileID=101"'
        in s["steps"]
    )
    assert "[图片未同步]" not in s["steps"]
    assert "signature=" not in s["steps"] and "data-file-id" not in s["steps"]
    assert len(s["description_writes"]) == 1
    assert rows(api)[0]["remote"] == 101
    assert push(api, s)["descriptionStatus"] == "succeeded"
    assert len(s["uploads"]) == 1 and len(s["description_writes"]) == 1
    assert len(s["remote"].writes) == 1


def test_existing_bug_supplements_inline_image_with_one_file_mapping(api, inline):
    s = inline
    assert push(api, s)["descriptionStatus"] == "none"
    seed(api, s, "later-image")
    change(api, StoredFile, "filename", "截图.png", file_id="later-image")
    change(api, StoredFile, "content_type", "image/png", file_id="later-image")
    html = '<p>现象与复现步骤<img data-file-id="later-image"></p>'
    change(api, Bug, "description_html", html, bug_id=s["bug"]["bugId"])
    status = api.get(s["url"], headers=s["owner"]).json()["data"]
    assert status["descriptionStatus"] == "pending" and status["ready"]
    assert push(api, s)["descriptionStatus"] == "succeeded"
    assert len(s["remote"].writes) == 1
    assert len(s["uploads"]) == 1
    html = '<p>现象与复现步骤<img data-file-id="later-image"><img data-file-id="later-image"></p>'
    change(api, Bug, "description_html", html, bug_id=s["bug"]["bugId"])
    assert push(api, s)["descriptionStatus"] == "succeeded"
    assert s["steps"].count("fileID=101") == 2
    assert len(s["uploads"]) == 1


def test_uncertain_description_is_verified_without_repeat_update_or_upload(api, inline):
    s = inline
    image(api, s)
    s["description_failure"] = "timeout"
    data = push(api, s)
    assert data["status"] == "succeeded" and data["descriptionStatus"] == "unknown"
    assert "secret-ticket" not in data["errorMessage"]
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["ready"]
    s["description_failure"] = ""
    assert push(api, s)["descriptionStatus"] == "succeeded"
    assert len(s["description_writes"]) == 1 and len(s["uploads"]) == 1
    assert len(s["remote"].writes) == 1


@pytest.mark.parametrize("change_style", [False, True])
def test_remote_description_changes_are_overwritten_and_retry_reuses_uploaded_image(
    api, inline, change_style
):
    s = inline
    image(api, s)
    s["attachment_failure"] = "known"
    assert push(api, s)["latestJob"]["jobStatus"] == "partial"
    baseline = s["steps"]
    changed = (
        baseline.replace("<p>", '<p style="color:red">', 1)
        if change_style
        else "<p>在禅道补充的说明</p>"
    )
    s["steps"] = changed
    s["attachment_failure"] = ""
    synced = push(api, s)
    assert synced["latestJob"]["jobStatus"] == "succeeded"
    assert synced["latestJob"]["result"]["steps"]["update_description"] == "succeeded"
    remote_file_id = rows(api)[0]["remote"]
    assert remote_file_id is not None
    assert "截图位置" in s["steps"] and f"fileID={remote_file_id}" in s["steps"]
    assert "在禅道补充的说明" not in s["steps"] and 'style="color:red"' not in s["steps"]
    assert len(s["description_writes"]) == 1
    count = len(s["uploads"])
    assert push(api, s)["descriptionStatus"] == "succeeded"
    assert len(s["uploads"]) == count
    assert len(s["description_writes"]) == 1


def test_missing_or_foreign_image_never_writes_description(api, inline):
    s = inline
    image(api, s)
    change(api, StoredFile, "resource_id", "other-bug", file_id="inline-image")
    response = dispatch_sync(api, s)
    assert response.status_code == 409, response.text
    assert not s["uploads"] and not s["description_writes"]


def test_native_zentao_urls_are_recognized_during_readback(api, inline):
    import re

    s = inline
    image(api, s)
    original = s["remote"].handle

    async def handle(request):
        result = await original(request)
        body = json.loads(request.content)
        if body.get("params", {}).get("name") == "get_bugs_bugID":
            data = result.json()
            bug = data["result"]["structuredContent"]["bug"]
            bug["steps"] = re.sub(
                r'src="\{(\d+)\.png\}"',
                r'src="/index.php?m=file&amp;f=read&amp;t=png&amp;fileID=\1" '
                r'onload="setImageSize(this,0)"',
                bug["steps"],
            )
            return httpx.Response(200, json=data)
        return result

    s["remote"].handle = handle
    assert push(api, s)["descriptionStatus"] == "succeeded"


def test_parallel_description_retry_updates_once(api, inline):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    s = inline
    image(api, s)
    entered, release = threading.Event(), threading.Event()
    original = s["remote"].handle

    async def handle(request):
        import asyncio

        body = json.loads(request.content)
        if body.get("params", {}).get("name") == "put_bugs_bugID":
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
        return await original(request)

    s["remote"].handle = handle
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(dispatch_sync, api, s, headers=s["owner"])
        assert entered.wait(timeout=10)
        try:
            other = dispatch_sync(api, s, headers=s["owner"])
            assert other.status_code == 409, other.text
        finally:
            release.set()
        assert first.result(timeout=10).json()["data"]["descriptionStatus"] == "succeeded"
    assert len(s["uploads"]) == 1 and len(s["description_writes"]) == 1


def test_revoked_authorization_before_description_write_prevents_update(api, inline):
    from testing_agent.models.integration_connection import IntegrationConnection

    s = inline
    image(api, s)
    original = s["remote"].handle
    revocations = []

    async def handle(request):
        result = await original(request)
        body = json.loads(request.content)
        if (
            body.get("params", {}).get("name") == "get_bugs_bugID"
            and s["uploads"]
            and not revocations
        ):
            revocations.append(True)
            from sqlalchemy import select

            async with api.app.state.test_sessions() as session:
                connection = await session.scalar(
                    select(IntegrationConnection).where(
                        IntegrationConnection.user_id == s["bug"]["reporterUserId"]
                    )
                )
                connection.status = "revoked"
                from testing_agent.services.worker_authorization import revoke_executions

                await revoke_executions(
                    session, actor=connection.user_id, connection_id=connection.connection_id
                )
                await session.commit()
        return result

    s["remote"].handle = handle
    result = push(api, s)
    assert result["latestJob"]["jobStatus"] == "canceled"
    assert revocations
    assert len(s["uploads"]) == 1
    assert not s["description_writes"]


def test_stale_preparation_resumes_without_reuploading_successful_files(api, inline):
    from datetime import UTC, datetime, timedelta

    from testing_agent.models.bug_zentao_push import BugZentaoPush

    s = inline
    image(api, s)
    s["attachment_failure"] = "known"
    assert push(api, s)["latestJob"]["jobStatus"] == "partial"
    change(api, BugZentaoPush, "description_status", "preparing", bug_id=s["bug"]["bugId"])
    change(
        api,
        BugZentaoPush,
        "description_updated_at",
        datetime.now(UTC) - timedelta(minutes=10),
        bug_id=s["bug"]["bugId"],
    )
    s["attachment_failure"] = ""
    assert push(api, s)["descriptionStatus"] == "succeeded"
    assert len(s["description_writes"]) == 1


def test_uncertain_write_with_unconfirmed_content_is_read_only(api, inline):
    s = inline
    image(api, s)
    s["description_failure"] = "timeout"
    assert push(api, s)["descriptionStatus"] == "unknown"
    s["steps"] = "<p>禅道侧另行修改，保留现场</p>"
    assert push(api, s)["descriptionStatus"] == "unknown"
    assert len(s["description_writes"]) == 1 and len(s["uploads"]) == 1
    assert s["steps"] == "<p>禅道侧另行修改，保留现场</p>"


@pytest.mark.parametrize("legacy_src", ["%7B101.png%7D", "{101.png}"])
def test_encoded_legacy_image_is_confirmed_failed_then_repaired_without_reupload(
    api, inline, legacy_src
):
    from testing_agent.models.bug_zentao_push import BugZentaoPush

    s = inline
    image(api, s)
    assert push(api, s)["descriptionStatus"] == "succeeded"
    legacy = '<p>截图位置</p><p><img src="{101.png}" ></p><p>后续说明</p>'
    encoded = f'<p>截图位置</p><p><img src="{legacy_src}" alt="{{101.png}}" /></p><p>后续说明</p>'
    s["steps"] = encoded
    change(api, BugZentaoPush, "description_status", "unknown", bug_id=s["bug"]["bugId"])
    # This is a pre-split write: it has no modern execution ledger.
    change(
        api,
        BugZentaoPush,
        "description_operation_id",
        "legacy-description-operation",
        bug_id=s["bug"]["bugId"],
    )
    change(
        api,
        BugZentaoPush,
        "description_sync_json",
        {
            "sourceHtml": '<p>截图位置</p><p><img data-file-id="inline-image"></p><p>后续说明</p>',
            "sourceHash": "legacy-hash",
            "desiredSteps": legacy,
            "expectedSteps": legacy.replace('<img src="{101.png}" >', "[图片未同步]"),
        },
        bug_id=s["bug"]["bugId"],
    )
    result = push(api, s)
    assert result["descriptionStatus"] == "succeeded", "已确认旧地址编码错误应恢复并修复"
    assert push(api, s)["descriptionStatus"] == "succeeded"
    assert "%7B" not in s["steps"] and 'src="{101.png}"' not in s["steps"]
    assert "m=file&amp;f=read&amp;t=png&amp;fileID=101" in s["steps"]
    assert len(s["uploads"]) == 1 and len(s["description_writes"]) == 2


@pytest.mark.parametrize(
    "file_url,expected",
    [
        (
            "/zentao/index.php?m=file&f=download&t=json&fileID=6",
            "https://zentao.test/zentao/index.php?m=file&f=read&t=png&fileID=6",
        ),
        ("/zentao/file-download-6.json", "https://zentao.test/zentao/file-read-6.png"),
        ("file-download-6-0-0.json", "https://zentao.test/zentao/file-read-6.png"),
    ],
)
def test_native_image_links_preserve_subpath_and_route_format(file_url, expected):
    from testing_agent.services.bug_zentao_description import native_image_url

    file = {"id": 6, "objectType": "bug", "objectID": 50, "extension": "png", "url": file_url}
    assert native_image_url(file, "https://zentao.test/zentao", 50) == expected


@pytest.mark.parametrize("mutation", ["foreign-host", "foreign-bug", "deleted", "wrong-id"])
def test_untrusted_native_file_links_are_rejected(mutation):
    from testing_agent.core.errors import AppError
    from testing_agent.services.bug_zentao_description import native_image_url

    file = {
        "id": 6,
        "objectType": "bug",
        "objectID": 50,
        "extension": "png",
        "url": "/index.php?m=file&f=download&t=json&fileID=6",
    }
    if mutation == "foreign-host":
        file["url"] = "https://other.test" + file["url"]
    elif mutation == "foreign-bug":
        file["objectID"] = 51
    elif mutation == "deleted":
        file["deleted"] = "1"
    else:
        file["url"] = "/index.php?m=file&f=download&t=json&fileID=7"
    with pytest.raises(AppError):
        native_image_url(file, "https://zentao.test", 50)


def test_encoding_of_a_new_native_url_does_not_trigger_repeated_repairs(api, inline):
    from testing_agent.models.bug_zentao_push import BugZentaoPush

    s = inline
    image(api, s)
    assert push(api, s)["descriptionStatus"] == "succeeded"
    s["steps"] = '<p>截图位置</p><p><img src="%7B101.png%7D" /></p><p>后续说明</p>'
    change(api, BugZentaoPush, "description_status", "unknown", bug_id=s["bug"]["bugId"])
    assert push(api, s)["descriptionStatus"] == "unknown"
    assert len(s["description_writes"]) == 1 and len(s["uploads"]) == 1
