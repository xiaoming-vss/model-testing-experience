"""Shared preparation for integration recovery tests; no collected cases."""

import json
from uuid import uuid4

import httpx

from support.bug_zentao_attachments import attachments as attachments
from support.integration_bug_api import api as api
from support.integration_bug_api import (
    claim,
    context,
    create_remote_mapping,
    prepare,
    result,
    rows,
    submit,
)
from support.integration_bug_api import integration as integration
from support.integration_bug_api import setup as setup
from testing_agent.models.bug_zentao_push import BugZentaoPush


def unknown_create(api, state):
    submit(api, state)
    claimed = claim(api, state)["job"]
    view, _ = context(api, state, claimed)
    permit, _ = prepare(
        api,
        state,
        claimed,
        "create_bug",
        {
            "payload": {**view["snapshot"]["createPayload"], "productID": 40},
        },
    )
    assert permit.status_code == 200, permit.text
    response, _ = result(
        api,
        state,
        claimed,
        "create_bug",
        permit.json(),
        status="unknown",
        payload={"errorCode": "remote_uncertain"},
    )
    assert response.status_code == 200, response.text
    return claimed, permit.json()


def unknown_fields(api, state, *, builds=None):
    linked = create_remote_mapping(api, state)
    done, _ = prepare(
        api, state, linked, "update_description", {"remoteBugId": 50}, decision="noop"
    )
    assert done.status_code == 200, done.text
    push = rows(api, BugZentaoPush)[0]
    response = api.post(
        f"/v1/bugs/{state['bug']['bugId']}/zentao-field-update-jobs",
        headers=state["owner"],
        json={
            "requestId": uuid4().hex,
            "expectedTarget": push.target_json,
            "expectedRemoteBugId": 50,
            "expectedOpenedBuild": ["trunk"],
            "expectedAssignedTo": "",
            "openedBuild": builds or ["trunk"],
            "assignedTo": "dev",
        },
    )
    assert response.status_code == 202, response.text
    claimed = claim(api, state)["job"]
    permit, _ = prepare(
        api,
        state,
        claimed,
        "update_fields",
        {
            "remoteBugId": 50,
            "before": {"openedBuild": ["trunk"], "assignedTo": ""},
            "payload": {"assignedTo": "dev", **({"openedBuild": builds} if builds else {})},
        },
    )
    assert permit.status_code == 200, permit.text
    response, _ = result(
        api,
        state,
        claimed,
        "update_fields",
        permit.json(),
        status="unknown",
        payload={"errorCode": "remote_uncertain"},
    )
    assert response.status_code == 200, response.text
    return claimed, permit.json()


def fields_readback(state, actual):
    original = state["remote"].handle

    async def read(request):
        response = await original(request)
        body = json.loads(request.content)
        if body.get("params", {}).get("name") == "get_bugs_bugID":
            data = response.json()
            data["result"]["structuredContent"]["bug"].update(product=40, **actual)
            return httpx.Response(200, json=data)
        return response

    state["remote"].handle = read
