import json

import httpx
import pytest

from testing_agent_integration_worker.core.errors import PreflightError, WriteUncertain
from testing_agent_integration_worker.gateways.mcp import McpCallError
from testing_agent_integration_worker.gateways.zentao import ZentaoGateway
from testing_agent_integration_worker.schemas.job import Access, JobInput, JobStep
from testing_agent_integration_worker.schemas.step import Operation
from testing_agent_integration_worker.services.description import description_input
from testing_agent_integration_worker.services.step_execution import StepExecution

TARGET = {"project": 10, "execution": 20, "story": 30}


@pytest.mark.parametrize("certainty", [False, True, None, "false"])
@pytest.mark.parametrize("code", ["source_unavailable", "file_integrity_failed"])
async def test_source_failure_requires_explicit_negative_write_certainty(certainty, code):
    calls = []

    def tools(name, arguments):
        calls.append(name)
        result = {"status": "error", "errorCode": code}
        if certainty is not None:
            result["uncertain"] = certainty
        return result

    async with ZentaoGateway(
        Access(endpoint="http://mcp.test", token="actor-key"), transport=transport_for(tools)
    ) as gateway:
        with pytest.raises(McpCallError) as error:
            await gateway.write(
                Operation(tool="upload_bug_attachment", arguments={}, timeout_seconds=180)
            )
    assert error.value.uncertain is (certainty is not False)
    assert calls == ["upload_bug_attachment"]


@pytest.mark.parametrize("foreign", [False, True])
@pytest.mark.parametrize("text_changed", [False, True])
async def test_existing_inline_image_uses_owned_metadata_when_bug_list_filters_it(
    foreign, text_changed
):
    calls = []
    instance = "https://zentao.example/sub"
    previous = (
        '<p>old<img src="'
        + instance
        + '/index.php?m=file&amp;f=read&amp;fileID=101&amp;t=png" ></p>'
    )

    def tools(name, args):
        calls.append(name)
        if name == "get_bugs_bugID":
            return {"bug": {"id": 50, **TARGET, "product": 40, "files": [], "steps": previous}}
        if name == "get_files_fileID":
            return {
                "file": {
                    "id": 101,
                    "objectType": "bug",
                    "objectID": 51 if foreign else 50,
                    "extension": "png",
                }
            }
        raise AssertionError("Description preparation must remain read-only")

    view = JobInput(
        job_id="j",
        job_status="running",
        task_type="zentao_bug_sync",
        protocol_version=1,
        result={},
        input_revision="input",
        target_revision="target",
        steps=[],
        mapping={"remoteBugId": 50, "productId": 40, "files": {"image": {"remoteFileId": 101}}},
        snapshot={
            "target": {**TARGET, "instanceUrl": instance},
            "source": {
                "html": f'<p>{"changed" if text_changed else "old"}<img data-file-id="image"></p>'
            },
            "existingPayload": {"productID": 40},
            "createPayload": {"steps": ""},
            "description": {
                "images": ["image"],
                "previousStatus": "succeeded",
                "expectedSteps": previous,
                "previous": {"desiredSteps": previous},
            },
        },
    )
    async with ZentaoGateway(
        Access(endpoint="http://mcp.test", token="actor-key"), transport=transport_for(tools)
    ) as gateway:
        if foreign or text_changed:
            with pytest.raises(PreflightError):
                await description_input(gateway, view)
        else:
            data, decision = await description_input(gateway, view)
            assert decision == "noop" and "fileID=101" in data["desiredSteps"]
            assert data["beforeSteps"] == previous
    assert calls == ["get_bugs_bugID", "get_files_fileID"]


def transport_for(tools, *, catalog=None):
    async def handle(request):
        body = json.loads(request.content)
        if body["method"] == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}
        elif body["method"] == "notifications/initialized":
            return httpx.Response(202)
        elif body["method"] == "tools/list":
            result = catalog(body["params"])
        else:
            result = {
                "structuredContent": tools(body["params"]["name"], body["params"]["arguments"])
            }
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    return httpx.MockTransport(handle)


async def test_choice_validation_follows_catalog_and_resource_paging():
    calls = []

    def catalog(params):
        if not params:
            return {"tools": [], "nextCursor": "second-page"}
        assert params == {"cursor": "second-page"}
        return {
            "tools": [
                {
                    "name": "get_executions_executionID_builds",
                    "inputSchema": {
                        "properties": {key: {} for key in ("executionID", "pageID", "recPerPage")}
                    },
                }
            ]
        }

    def tools(name, args):
        calls.append((name, args))
        if name == "get_users":
            return {"users": [{"id": 1, "account": "dev"}], "count": 1}
        return {
            "builds": [{"id": 59 + args["pageID"], "project": 10, "execution": 20, "product": 40}],
            "pager": {"recTotal": "2"},
        }

    async with ZentaoGateway(
        Access(endpoint="http://mcp.test", token="actor-key"),
        transport=transport_for(tools, catalog=catalog),
    ) as gateway:
        await gateway.validate_choices(TARGET, 40, {"openedBuild": ["61"], "assignedTo": "dev"})
    assert [args["pageID"] for name, args in calls if name.endswith("builds")] == [1, 2]


@pytest.mark.parametrize("deleted", [" yes ", "on", True])
async def test_deleted_assignees_cannot_receive_a_write_permit(deleted):
    def tools(name, args):
        return {"users": [{"id": 1, "account": "dev", "deleted": deleted}], "total": 1}

    async with ZentaoGateway(
        Access(endpoint="http://mcp.test", token="actor-key"), transport=transport_for(tools)
    ) as gateway:
        with pytest.raises(PreflightError) as error:
            await gateway.validate_choices(TARGET, 40, {"assignedTo": "dev"})
    assert error.value.code == "remote_rejected"


@pytest.mark.parametrize("total", [True, -1, 0, "invalid"])
async def test_malformed_paging_cannot_be_treated_as_complete(total):
    def tools(name, args):
        return {"users": [{"id": 1, "account": "dev"}], "total": total}

    async with ZentaoGateway(
        Access(endpoint="http://mcp.test", token="actor-key"), transport=transport_for(tools)
    ) as gateway:
        with pytest.raises(PreflightError) as error:
            await gateway.validate_choices(TARGET, 40, {"assignedTo": "dev"})
    assert error.value.code == "remote_unavailable"


@pytest.mark.parametrize(
    "src", ["{101.png}", "%7B101.png%7D", "/index.php?m=file&f=read&t=png&fileID=101"]
)
async def test_description_readback_requires_a_working_native_image(src):
    target = {**TARGET, "instanceUrl": "https://zentao.example"}
    desired = '<p><img src="/index.php?m=file&f=read&t=png&fileID=101"></p>'

    class Gateway:
        async def verify_instance(self, value):
            assert value == target

        async def bug(self, identifier, value, product):
            assert identifier == 50 and product == 40
            return {"steps": f'<p><img src="{src}"></p>'}

    view = JobInput(
        job_id="j",
        job_status="running",
        task_type="zentao_bug_sync",
        protocol_version=1,
        result={},
        input_revision="i",
        target_revision="t",
        steps=[],
        mapping={"remoteBugId": 50, "productId": 40},
        snapshot={"target": target, "existingPayload": {}},
    )
    step = JobStep(
        step_key="update_description",
        kind="update_description",
        status="write_intent",
        dependencies=[],
        input={},
    )
    execution = StepExecution(None, None, None)
    if src.startswith("/"):
        assert (
            await execution.readback(Gateway(), view, step, {"desiredSteps": desired})
        ).description_hash
    else:
        with pytest.raises(WriteUncertain):
            await execution.readback(Gateway(), view, step, {"desiredSteps": desired})
