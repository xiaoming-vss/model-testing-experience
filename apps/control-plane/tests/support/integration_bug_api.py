"""Shared preparation for integration bug api tests; no collected cases."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from support.bug_zentao_push_api import setup as setup
from support.project_api import api as api
from testing_agent.core.config import IntegrationExecutionSettings, get_settings

PREFIX = "/internal/integration-worker"


@pytest.fixture
def integration(api, setup):
    settings = replace(
        get_settings(),
        integration_worker_key="integration-rpc-test",
        integration_execution=IntegrationExecutionSettings(
            enabled=True,
            all_projects=True,
            runtime_generation="rpc-runtime",
        ),
    )
    api.app.dependency_overrides[get_settings] = lambda: settings
    api.app.state.settings = settings
    engine = api.app.state.test_sessions.kw["bind"]

    @event.listens_for(engine.sync_engine, "begin")
    def explicit_transaction(connection):
        connection.exec_driver_sql("BEGIN")

    setup["headers"] = {"X-Worker-Token": settings.integration_worker_key}
    setup["createUrl"] = f"/v1/bugs/{setup['bug']['bugId']}/zentao-sync-jobs"
    return setup


def submit(api, state, **extra):
    body = {"requestId": uuid4().hex, **extra}
    response = api.post(state["createUrl"], headers=state["owner"], json=body)
    assert response.status_code == 202, response.text
    return response.json()["data"], body


def claim(api, state, *, request=None, worker="worker-a"):
    response = api.post(
        PREFIX + "/jobs/claim",
        headers=state["headers"],
        json={
            "workerId": worker,
            "claimRequestId": request or uuid4().hex,
            "protocolVersions": [1],
            "taskTypes": ["zentao_bug_sync", "zentao_bug_fields_update"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def identity(claimed):
    return {key: claimed[key] for key in ("workerId", "claimGeneration", "runtimeGeneration")}


def context(api, state, claimed):
    ident = identity(claimed)
    root = PREFIX + "/jobs/" + claimed["jobId"]
    view = api.get(root + "/input", headers=state["headers"], params=ident)
    assert view.status_code == 200, view.text
    access = api.post(root + "/access", headers=state["headers"], json=ident)
    assert access.status_code == 200, access.text
    assert access.headers["Cache-Control"] == "no-store"
    return view.json(), access.json()


def prepare(api, state, claimed, step, data, *, decision="write", request=None):
    view, access = context(api, state, claimed)
    body = {
        **identity(claimed),
        "prepareRequestId": request or uuid4().hex,
        "inputRevision": view["inputRevision"],
        "targetRevision": view["targetRevision"],
        "accessRevision": access["accessRevision"],
        "input": data,
        "decision": decision,
    }
    response = api.post(
        PREFIX + f"/jobs/{claimed['jobId']}/steps/{step}/prepare",
        headers=state["headers"],
        json=body,
    )
    return response, body


def result(
    api,
    state,
    claimed,
    step,
    permit,
    *,
    event=None,
    status="succeeded",
    payload=None,
    evidence=False,
):
    body = {
        **identity(claimed),
        "eventId": event or uuid4().hex,
        "operationId": permit["operationId"],
        "status": status,
        "result": payload if payload is not None else {"remoteBugId": 50},
    }
    suffix = "evidence" if evidence else "result"
    response = api.post(
        PREFIX + f"/jobs/{claimed['jobId']}/steps/{step}/{suffix}",
        headers=state["headers"],
        json=body,
    )
    return response, body


def rows(api, model):
    async def read():
        async with api.app.state.test_sessions() as session:
            return list(await session.scalars(select(model)))

    return asyncio.run(read())


def create_remote_mapping(api, state):
    submit(api, state)
    claimed = claim(api, state)["job"]
    view, _ = context(api, state, claimed)
    prepared, _ = prepare(
        api,
        state,
        claimed,
        "create_bug",
        {
            "payload": {**view["snapshot"]["createPayload"], "productID": 40},
        },
    )
    assert prepared.status_code == 200, prepared.text
    receipt, _ = result(api, state, claimed, "create_bug", prepared.json())
    assert receipt.status_code == 200, receipt.text
    return claimed
