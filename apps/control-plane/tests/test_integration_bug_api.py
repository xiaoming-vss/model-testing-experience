"""Real browser/internal HTTP protocol and domain transactions; no remote execution in CP."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from test_bug_zentao_push_api import change
from test_bug_zentao_push_api import setup as setup
from test_project_membership_api import account
from test_project_membership_api import api as api

from testing_agent.core.config import IntegrationExecutionSettings, get_settings
from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_job import IntegrationJob, IntegrationJobStep

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


def test_legacy_confirmed_target_is_enriched_without_rewriting_history(api, integration):
    state = integration
    confirmed = create_remote_mapping(api, state)
    done, _ = prepare(
        api, state, confirmed, "update_description", {"remoteBugId": 50}, decision="noop"
    )
    assert done.status_code == 200, done.text
    linked = rows(api, BugZentaoPush)[0]
    historical = {key: linked.target_json[key] for key in ("project", "execution", "story")}
    change(api, BugZentaoPush, "target_json", historical, bug_id=state["bug"]["bugId"])
    submitted, _ = submit(api, state)
    claimed = claim(api, state)["job"]
    assert claimed["jobId"] == submitted["jobId"]
    view, _ = context(api, state, claimed)
    assert view["snapshot"]["target"]["instanceUrl"] == linked.instance_url
    assert view["snapshot"]["target"]["mcpServiceId"] == linked.service_id
    assert view["mapping"]["remoteBugId"] == 50
    assert rows(api, BugZentaoPush)[0].target_json == historical
    assert state["remote"].writes == []


@pytest.mark.parametrize("instance", ["http://other-instance.test", None, 42])
def test_contradictory_confirmed_instance_is_rejected(api, integration, instance):
    state = integration
    create_remote_mapping(api, state)
    linked = rows(api, BugZentaoPush)[0]
    change(
        api,
        BugZentaoPush,
        "target_json",
        {**linked.target_json, "instanceUrl": instance},
        bug_id=state["bug"]["bugId"],
    )
    response = api.post(state["createUrl"], headers=state["owner"], json={"requestId": uuid4().hex})
    assert response.status_code == 409, response.text
    assert len(rows(api, IntegrationJob)) == 1  # Only the already confirmed mapping's task.
    assert state["remote"].writes == []


def test_submission_is_local_idempotent_and_legacy_writer_is_absent(api, integration):
    state = integration
    before = len(state["remote"].headers)
    submitted, body = submit(api, state)
    assert submitted["jobStatus"] == "queued"
    repeated = api.post(state["createUrl"], headers=state["owner"], json=body)
    assert repeated.json()["data"]["jobId"] == submitted["jobId"]
    assert len(rows(api, IntegrationJob)) == 1
    assert len(state["remote"].headers) == before
    status = api.get(state["url"], headers=state["owner"])
    assert status.status_code == 200, status.text
    assert status.json()["data"]["executionMode"] == "worker"
    assert status.json()["data"]["activeJob"]["jobId"] == submitted["jobId"]
    assert api.post(state["url"], headers=state["owner"]).status_code == 405
    assert len(state["remote"].headers) == before
    assert state["remote"].writes == []


def test_claim_prepare_receipt_and_final_noop_update_domains_atomically(api, integration):
    state = integration
    submitted, _ = submit(api, state)
    claimed = claim(api, state)["job"]
    assert claimed["jobId"] == submitted["jobId"]
    view, _ = context(api, state, claimed)
    payload = {**view["snapshot"]["createPayload"], "productID": 40}
    prepared, body = prepare(api, state, claimed, "create_bug", {"payload": payload})
    assert prepared.status_code == 200, prepared.text
    permit = prepared.json()
    assert permit["writeAllowed"]
    assert permit["operation"]["tool"] == "post_bugs"
    assert permit["access"]["token"] == "owner-secret"
    assert prepared.headers["Cache-Control"] == "no-store"
    assert state["remote"].writes == []
    assert rows(api, BugZentaoPush)[0].status == "creating"
    duplicate = api.post(
        PREFIX + f"/jobs/{claimed['jobId']}/steps/create_bug/prepare",
        headers=state["headers"],
        json=body,
    )
    assert duplicate.status_code == 200, duplicate.text
    assert not duplicate.json()["writeAllowed"]
    assert "access" not in duplicate.json()
    receipt, event = result(api, state, claimed, "create_bug", permit)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["jobStatus"] == "running"
    assert rows(api, BugZentaoPush)[0].remote_bug_id == 50
    assert rows(api, IntegrationJobStep)[0].status == "succeeded"
    assert "owner-secret" not in str(rows(api, IntegrationJob)[0].snapshot_json)
    duplicate = api.post(
        PREFIX + f"/jobs/{claimed['jobId']}/steps/create_bug/result",
        headers=state["headers"],
        json=event,
    )
    assert duplicate.json() == receipt.json()
    done, _ = prepare(
        api, state, claimed, "update_description", {"remoteBugId": 50}, decision="noop"
    )
    assert done.status_code == 200, done.text
    assert done.json()["jobStatus"] == "succeeded"
    assert rows(api, IntegrationJob)[0].active_scope is None
    activities = [row for row in rows(api, BugActivity) if row.action == "zentao_sync_job"]
    assert len(activities) == 1
    done_again = api.post(
        PREFIX + f"/jobs/{claimed['jobId']}/completed",
        headers=state["headers"],
        json=identity(claimed),
    )
    assert done_again.status_code == 200, done_again.text
    assert len([row for row in rows(api, BugActivity) if row.action == "zentao_sync_job"]) == 1
    status = api.get(state["url"], headers=state["owner"]).json()["data"]
    assert status["activeJob"] is None and status["latestJob"]["jobStatus"] == "succeeded"


def test_input_changes_stop_prepare_without_creating_domain_write_intent(api, integration):
    state = integration
    submit(api, state)
    claimed = claim(api, state)["job"]
    view, access = context(api, state, claimed)
    change(api, Bug, "description_html", "<p>changed</p>", bug_id=state["bug"]["bugId"])
    response = api.post(
        PREFIX + f"/jobs/{claimed['jobId']}/steps/create_bug/prepare",
        headers=state["headers"],
        json={
            **identity(claimed),
            "prepareRequestId": uuid4().hex,
            "inputRevision": view["inputRevision"],
            "targetRevision": view["targetRevision"],
            "accessRevision": access["accessRevision"],
            "input": {"payload": {**view["snapshot"]["createPayload"], "productID": 40}},
        },
    )
    assert response.status_code == 409, response.text
    assert rows(api, BugZentaoPush) == []
    assert rows(api, IntegrationJobStep)[0].status == "pending"
    failure = api.post(
        PREFIX + f"/jobs/{claimed['jobId']}/steps/create_bug/preflight-failure",
        headers=state["headers"],
        json={
            **identity(claimed),
            "eventId": uuid4().hex,
            "errorCode": "input_changed",
        },
    )
    assert failure.status_code == 200, failure.text
    assert failure.json()["jobStatus"] == "failed"


def test_job_summary_is_bug_scoped_and_does_not_disclose_frozen_inputs(api, integration):
    state = integration
    submitted, _ = submit(api, state)
    _, outsider = account(api, "integration-outsider")
    url = f"/v1/bugs/{state['bug']['bugId']}/zentao-jobs/{submitted['jobId']}"
    assert api.get(url, headers=outsider).status_code in (403, 404)
    response = api.get(url, headers=state["owner"])
    assert response.status_code == 200, response.text
    assert "snapshot" not in response.text and "connectionId" not in response.text
    assert "owner-secret" not in response.text


def test_old_worker_credentials_cannot_claim_integration_jobs(api, integration):
    old = get_settings().worker_key or "old"
    response = api.post(
        PREFIX + "/jobs/claim",
        headers={"X-Worker-Token": old},
        json={
            "workerId": "old-worker",
            "claimRequestId": "old-claim",
            "protocolVersions": [1],
            "taskTypes": ["zentao_bug_sync"],
        },
    )
    assert response.status_code == 401


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


def test_attachment_ticket_is_issued_only_for_the_live_prepared_file(api, integration, monkeypatch):
    from test_bug_zentao_attachments import seed

    from testing_agent.services.stored_file import StoredFileService

    state = integration
    seed(api, state)
    tickets = []

    async def ticket(self, row):
        tickets.append(row.file_id)
        return {"url": "http://s3.test/file?X-Amz-Signature=private-signature", "expiresIn": 900}

    monkeypatch.setattr(StoredFileService, "ticket", ticket)
    claimed = create_remote_mapping(api, state)
    assert tickets == []
    permit, _ = prepare(
        api,
        state,
        claimed,
        "upload_attachment:attachment-1",
        {
            "fileId": "attachment-1",
            "remoteBugId": 50,
        },
    )
    assert permit.status_code == 200, permit.text
    assert tickets == ["attachment-1"]
    assert permit.json()["operation"]["timeoutSeconds"] == 180
    assert "X-Amz-Signature" in permit.json()["operation"]["arguments"]["downloadUrl"]
    assert "private-signature" not in str(rows(api, IntegrationJobStep)[1].input_json)
    receipt, _ = result(
        api,
        state,
        claimed,
        "upload_attachment:attachment-1",
        permit.json(),
        payload={"remoteFileId": 101},
    )
    assert receipt.status_code == 200, receipt.text
    assert rows(api, BugZentaoAttachment)[0].remote_file_id == 101
    assert receipt.json()["mapping"]["files"]["attachment-1"]["remoteFileId"] == 101
    done, _ = prepare(
        api, state, claimed, "update_description", {"remoteBugId": 50}, decision="noop"
    )
    assert done.status_code == 200, done.text
    assert done.json()["jobStatus"] == "succeeded"


def test_description_updates_use_frozen_source_and_native_mapping(api, integration, monkeypatch):
    from test_bug_zentao_attachments import seed

    from testing_agent.models.stored_file import StoredFile
    from testing_agent.services.bug_zentao_description import source_hash
    from testing_agent.services.stored_file import StoredFileService

    state = integration
    seed(api, state)
    change(api, StoredFile, "content_type", "image/png", file_id="attachment-1")
    change(
        api,
        Bug,
        "description_html",
        '<p>image<img data-file-id="attachment-1"></p>',
        bug_id=state["bug"]["bugId"],
    )

    async def ticket(self, row):
        return {"url": "http://s3.test/image", "expiresIn": 900}

    monkeypatch.setattr(StoredFileService, "ticket", ticket)
    claimed = create_remote_mapping(api, state)
    uploaded, _ = prepare(
        api,
        state,
        claimed,
        "upload_attachment:attachment-1",
        {
            "fileId": "attachment-1",
            "remoteBugId": 50,
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    receipt, _ = result(
        api,
        state,
        claimed,
        "upload_attachment:attachment-1",
        uploaded.json(),
        payload={"remoteFileId": 101},
    )
    assert receipt.status_code == 200, receipt.text
    desired = '<p>image<img src="http://zentao.test/file-read-101.png" ></p>'
    data = {
        "remoteBugId": 50,
        "beforeSteps": "<p>image</p>",
        "desiredSteps": desired,
        "imagePaths": {"attachment-1": "http://zentao.test/file-read-101.png"},
        "imageExtensions": {"attachment-1": "png"},
    }
    description, _ = prepare(api, state, claimed, "update_description", data)
    assert description.status_code == 200, description.text
    assert description.json()["operation"]["arguments"]["payload"] == {"steps": desired}
    completed, _ = result(
        api,
        state,
        claimed,
        "update_description",
        description.json(),
        payload={"descriptionHash": source_hash(desired)},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["jobStatus"] == "succeeded"
    push = rows(api, BugZentaoPush)[0]
    assert push.description_status == "succeeded"
    assert (
        push.description_sync_json["sourceHtml"] == '<p>image<img data-file-id="attachment-1"></p>'
    )


def test_fields_task_only_writes_changed_fields_and_persists_actual_readback(api, integration):
    state = integration
    claimed = create_remote_mapping(api, state)
    done, _ = prepare(
        api, state, claimed, "update_description", {"remoteBugId": 50}, decision="noop"
    )
    assert done.status_code == 200, done.text
    linked = rows(api, BugZentaoPush)[0]
    response = api.post(
        f"/v1/bugs/{state['bug']['bugId']}/zentao-field-update-jobs",
        headers=state["owner"],
        json={
            "requestId": uuid4().hex,
            "expectedTarget": linked.target_json,
            "expectedRemoteBugId": 50,
            "openedBuild": ["trunk"],
            "assignedTo": "dev",
            "expectedOpenedBuild": ["trunk"],
            "expectedAssignedTo": "",
        },
    )
    assert response.status_code == 202, response.text
    field_job = claim(api, state)["job"]
    permit, _ = prepare(
        api,
        state,
        field_job,
        "update_fields",
        {
            "remoteBugId": 50,
            "before": {"openedBuild": ["trunk"], "assignedTo": ""},
            "payload": {"assignedTo": "dev"},
        },
    )
    assert permit.status_code == 200, permit.text
    assert permit.json()["operation"]["arguments"]["payload"] == {"assignedTo": "dev"}
    completed, _ = result(
        api,
        state,
        field_job,
        "update_fields",
        permit.json(),
        payload={
            "openedBuild": ["trunk"],
            "assignedTo": "dev",
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["jobStatus"] == "succeeded"
    linked = rows(api, BugZentaoPush)[0]
    assert linked.payload_json["assignedTo"] == "dev"
    assert linked.payload_json["_fieldUpdate"]["status"] == "succeeded"


def test_revocation_cancels_queue_without_borrowing_another_members_token(api, integration):
    state = integration
    submit(api, state)
    revoked = api.delete(f"{state['path']}/{state['sid']}/authorization", headers=state["owner"])
    assert revoked.status_code == 200, revoked.text
    assert rows(api, IntegrationJob)[0].status == "canceled"
    assert claim(api, state)["job"] is None
    assert state["remote"].writes == []


def test_revocation_retains_unknown_write_and_accepts_only_old_operation_evidence(api, integration):
    state = integration
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
    revoked = api.delete(f"{state['path']}/{state['sid']}/authorization", headers=state["owner"])
    assert revoked.status_code == 200, revoked.text
    assert rows(api, IntegrationJob)[0].status == "unknown"
    assert rows(api, BugZentaoPush)[0].status == "unknown"
    denied = api.post(
        PREFIX + f"/jobs/{claimed['jobId']}/access",
        headers=state["headers"],
        json=identity(claimed),
    )
    assert denied.status_code in (403, 409)
    evidence, _ = result(api, state, claimed, "create_bug", permit.json(), evidence=True)
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["jobStatus"] == "canceled"
    assert rows(api, BugZentaoPush)[0].remote_bug_id == 50


def test_member_downgrade_revokes_integration_but_keeps_bug_read_access(api, integration):

    state = integration
    member, headers = account(api, "integration-member")
    assert (
        api.post(
            f"/v1/projects/{state['pid']}/members",
            headers=state["owner"],
            json={
                "name": "integration-member",
                "role": "member",
            },
        ).status_code
        == 200
    )
    assert (
        api.put(
            f"{state['path']}/{state['sid']}/authorization",
            headers=headers,
            json={"token": "member-secret"},
        ).status_code
        == 200
    )
    admitted = api.post(state["createUrl"], headers=headers, json={"requestId": uuid4().hex})
    assert admitted.status_code == 202, admitted.text
    downgraded = api.patch(
        f"/v1/projects/{state['pid']}/members/{member['userId']}",
        headers=state["owner"],
        json={"role": "viewer"},
    )
    assert downgraded.status_code == 200, downgraded.text
    assert rows(api, IntegrationJob)[0].status == "canceled"
    assert api.get(f"/v1/bugs/{state['bug']['bugId']}", headers=headers).status_code == 200


def test_known_aborted_local_transaction_retries_without_remote_execution(
    api, integration, monkeypatch
):
    import pymysql
    from sqlalchemy.exc import OperationalError

    from testing_agent.services.integration_bug_steps import IntegrationBugSteps

    state = integration
    submit(api, state)
    claimed = claim(api, state)["job"]
    view, _ = context(api, state, claimed)
    original = IntegrationBugSteps.reserve
    calls = []

    async def reserve(self, job, step):
        await original(self, job, step)
        calls.append(step.operation_id)
        if len(calls) == 1:
            raise OperationalError(None, None, pymysql.OperationalError(1213, "isolated deadlock"))

    monkeypatch.setattr(IntegrationBugSteps, "reserve", reserve)
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
    assert len(calls) == 2 and calls[0] != calls[1]
    assert len(rows(api, BugZentaoPush)) == 1
    assert rows(api, BugZentaoPush)[0].operation_id == permit.json()["operationId"]
    assert rows(api, IntegrationJobStep)[0].status == "write_intent"
    assert state["remote"].writes == []


def test_queue_http_shows_recent_capability_and_keeps_internal_worker_input_compatible(
    api, integration
):
    state = integration
    submitted, _ = submit(api, state)
    url = f"/v1/bugs/{state['bug']['bugId']}/zentao-jobs/{submitted['jobId']}"
    queued = api.get(url, headers=state["owner"]).json()["data"]
    assert queued["queueReason"] == "worker_offline" and queued["queueWaitSeconds"] >= 0
    unsupported = api.post(
        PREFIX + "/jobs/claim",
        headers=state["headers"],
        json={
            "workerId": "future-worker",
            "claimRequestId": "future-claim",
            "protocolVersions": [2],
            "taskTypes": ["future_type"],
        },
    )
    assert unsupported.status_code == 200 and unsupported.json()["job"] is None
    assert (
        api.get(url, headers=state["owner"]).json()["data"]["queueReason"] == "worker_incompatible"
    )
    assert rows(api, IntegrationJob)[0].status == "queued"
    claimed = claim(api, state)["job"]
    view, _ = context(api, state, claimed)
    assert "queueReason" not in view and "queueWaitSeconds" not in view
    response = api.post(
        PREFIX + f"/jobs/{claimed['jobId']}/heartbeat",
        headers=state["headers"],
        json=identity(claimed),
    )
    assert response.status_code == 200
    from testing_agent.models.integration_job import IntegrationWorkerPresence

    worker = next(
        w for w in rows(api, IntegrationWorkerPresence) if w.worker_id == claimed["workerId"]
    )
    assert worker.last_heartbeat_at is not None
    assert "future-worker" not in str(api.get(url, headers=state["owner"]).json())


@pytest.mark.parametrize("unknown", [False, True])
def test_paused_execution_keeps_task_queries_and_blocks_legacy_fallback(api, integration, unknown):
    state = integration
    if unknown:
        from test_integration_recovery import unknown_create

        unknown_create(api, state)
    else:
        submit(api, state)
    current = api.app.state.settings
    paused = replace(
        current, integration_execution=replace(current.integration_execution, enabled=False)
    )
    api.app.dependency_overrides[get_settings] = lambda: paused
    status = api.get(f"/v1/bugs/{state['bug']['bugId']}/zentao-push", headers=state["owner"])
    assert status.status_code == 200, status.text
    data = status.json()["data"]
    assert data["executionMode"] == "worker" and data["ready"] is False
    if not unknown:
        assert data["activeJob"]["queueReason"] == "paused"
    response = api.post(f"/v1/bugs/{state['bug']['bugId']}/zentao-push", headers=state["owner"])
    assert response.status_code == 405, response.text
    assert response.headers["allow"] == "GET"
    assert state["remote"].writes == []
