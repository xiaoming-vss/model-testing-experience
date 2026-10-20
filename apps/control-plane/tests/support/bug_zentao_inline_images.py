"""Shared preparation for bug zentao inline images tests; no collected cases."""

import json

import httpx
import pytest
from integration_test_driver import enable

from support.bug_zentao_attachments import attachments as attachments
from support.bug_zentao_attachments import seed
from support.bug_zentao_push_api import change
from support.bug_zentao_push_api import setup as setup
from support.project_api import api as api
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
