"""Real HTTP, ledger and domain transactions for trusted read-only recovery."""

import json

import httpx
import pytest
from support.bug_zentao_attachments import attachments as attachments
from support.bug_zentao_attachments import seed
from support.bug_zentao_inline_images import image
from support.bug_zentao_push_api import change
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
from support.integration_recovery import (
    fields_readback as fields_readback,
)
from support.integration_recovery import (
    unknown_create as unknown_create,
)
from support.integration_recovery import (
    unknown_fields as unknown_fields,
)

from testing_agent.core.errors import AppError
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_job import IntegrationJob, IntegrationJobStep
from testing_agent.services.bug_zentao_description import source_hash
from testing_agent.services.integration_job import IntegrationJobService


def test_create_reconcile_recovers_original_step_without_replaying_dependencies(api, integration):
    state = integration
    claimed, permit = unknown_create(api, state)
    recovered = api.post(
        state["url"] + "/reconcile", headers=state["owner"], json={"remoteBugId": 50}
    )
    assert recovered.status_code == 200, recovered.text
    job = rows(api, IntegrationJob)[0]
    assert job.status == "partial" and job.mapping_json["remoteBugId"] == 50
    steps = rows(api, IntegrationJobStep)
    assert [step.status for step in steps] == ["succeeded", "blocked"]
    assert steps[0].operation_id == permit["operationId"]
    assert steps[0].receipts_json[-1]["source"] == "readonly_recovery"
    before = len(rows(api, BugActivity))
    response, event = result(api, state, claimed, "create_bug", permit, evidence=True)
    assert response.status_code == 200, response.text
    response, _ = result(
        api, state, claimed, "create_bug", permit, event=event["eventId"], evidence=True
    )
    assert response.status_code == 200, response.text
    assert len(rows(api, BugActivity)) == before
    assert state["remote"].writes == []


@pytest.mark.parametrize(
    "status,payload",
    [
        ("succeeded", {"remoteBugId": 51}),
        ("unknown", {"errorCode": "remote_uncertain"}),
        ("failed", {"errorCode": "remote_rejected"}),
    ],
)
def test_late_evidence_cannot_replace_a_verified_fact(api, integration, status, payload):
    state = integration
    claimed, permit = unknown_create(api, state)
    assert (
        api.post(
            state["url"] + "/reconcile", headers=state["owner"], json={"remoteBugId": 50}
        ).status_code
        == 200
    )
    response, _ = result(
        api, state, claimed, "create_bug", permit, status=status, payload=payload, evidence=True
    )
    assert response.status_code == 409
    assert rows(api, BugZentaoPush)[0].remote_bug_id == 50
    assert rows(api, IntegrationJobStep)[0].status == "succeeded"


def test_recovery_rolls_back_domain_and_ledger_together(api, integration, monkeypatch):
    state = integration
    unknown_create(api, state)
    finish = IntegrationJobService.finish

    async def fail_after_ledger_update(self, job):
        await finish(self, job)
        raise AppError(409, "isolated recovery transaction failure", 409)

    monkeypatch.setattr(IntegrationJobService, "finish", fail_after_ledger_update)
    before = len(rows(api, BugActivity))
    response = api.post(
        state["url"] + "/reconcile", headers=state["owner"], json={"remoteBugId": 50}
    )
    assert response.status_code == 409, response.text
    assert rows(api, BugZentaoPush)[0].status == "unknown"
    assert rows(api, IntegrationJob)[0].status == "unknown"
    assert rows(api, IntegrationJobStep)[0].status == "unknown"
    assert len(rows(api, BugActivity)) == before


def test_create_recovery_rejects_a_bug_with_the_wrong_original_product(api, integration):
    state = integration
    unknown_create(api, state)
    fields_readback(state, {})
    original = state["remote"].handle

    async def wrong_product(request):
        response = await original(request)
        if json.loads(request.content).get("params", {}).get("name") == "get_bugs_bugID":
            data = response.json()
            data["result"]["structuredContent"]["bug"]["product"] = 41
            return httpx.Response(200, json=data)
        return response

    state["remote"].handle = wrong_product
    response = api.post(
        state["url"] + "/reconcile", headers=state["owner"], json={"remoteBugId": 50}
    )
    assert response.status_code == 400, response.text
    assert rows(api, BugZentaoPush)[0].status == "unknown"
    assert rows(api, IntegrationJob)[0].status == "unknown"


@pytest.mark.parametrize("actual,expected", [("dev", 200), ("external", 409)])
def test_options_recovery_updates_fields_and_task_only_for_original_desired_values(
    api,
    integration,
    actual,
    expected,
):
    state = integration
    claimed, permit = unknown_fields(api, state)
    fields_readback(state, {"openedBuild": ["trunk"], "assignedTo": actual})
    response = api.get(state["url"] + "/options", headers=state["owner"])
    assert response.status_code == expected, response.text
    job = next(job for job in rows(api, IntegrationJob) if job.job_id == claimed["jobId"])
    assert job.status == ("succeeded" if expected == 200 else "unknown")
    assert rows(api, BugZentaoPush)[0].payload_json["_fieldUpdate"]["status"] == job.status
    if expected == 200:
        response, _ = result(
            api,
            state,
            claimed,
            "update_fields",
            permit,
            evidence=True,
            payload={"openedBuild": ["trunk"], "assignedTo": actual},
        )
        assert response.status_code == 200, response.text
    assert not any(name == "put_bugs_bugID" for name, _ in state["remote"].calls)


def test_field_recovery_is_fenced_by_a_new_active_sync(api, integration):
    state = integration
    claimed, _ = unknown_fields(api, state)
    fields_readback(state, {"openedBuild": ["trunk"], "assignedTo": "dev"})
    submit(api, state)
    response = api.get(state["url"] + "/options", headers=state["owner"])
    assert response.status_code == 409, response.text
    job = next(job for job in rows(api, IntegrationJob) if job.job_id == claimed["jobId"])
    assert job.status == "unknown"


def test_already_recovered_creation_is_joined_to_old_ledger_by_a_verified_noop(api, integration):
    state = integration
    old, permit = unknown_create(api, state)
    change(api, BugZentaoPush, "status", "succeeded", bug_id=state["bug"]["bugId"])
    change(api, BugZentaoPush, "remote_bug_id", 50, bug_id=state["bug"]["bugId"])
    submit(api, state)
    new = claim(api, state)["job"]
    response, _ = prepare(
        api, state, new, "create_bug", {"result": {"remoteBugId": 50}}, decision="noop"
    )
    assert response.status_code == 200, response.text
    original = next(job for job in rows(api, IntegrationJob) if job.job_id == old["jobId"])
    assert original.status == "partial" and original.mapping_json["remoteBugId"] == 50
    step = next(
        step for step in rows(api, IntegrationJobStep) if step.operation_id == permit["operationId"]
    )
    assert step.status == "succeeded"
    assert state["remote"].writes == []


def test_already_recovered_fields_are_joined_to_old_ledger_by_current_readback(api, integration):
    state = integration
    old, _ = unknown_fields(api, state)
    row = rows(api, BugZentaoPush)[0]
    payload = {
        **row.payload_json,
        "openedBuild": ["trunk"],
        "assignedTo": "dev",
        "_fieldUpdate": {**row.payload_json["_fieldUpdate"], "status": "succeeded"},
    }
    change(api, BugZentaoPush, "payload_json", payload, bug_id=state["bug"]["bugId"])
    fields_readback(state, {"openedBuild": ["trunk"], "assignedTo": "dev"})
    response = api.get(state["url"] + "/options", headers=state["owner"])
    assert response.status_code == 200, response.text
    original = next(job for job in rows(api, IntegrationJob) if job.job_id == old["jobId"])
    assert original.status == "succeeded"
    assert not any(name == "put_bugs_bugID" for name, _ in state["remote"].calls)


def test_fields_recovery_and_evidence_preserve_set_semantics_for_build_order(api, integration):
    state = integration
    claimed, permit = unknown_fields(api, state, builds=["60", "61"])
    fields_readback(state, {"openedBuild": ["61", "60"], "assignedTo": "dev"})
    assert api.get(state["url"] + "/options", headers=state["owner"]).status_code == 200
    # A later read or the original result outbox can use the opposite array order.
    fields_readback(state, {"openedBuild": ["60", "61"], "assignedTo": "dev"})
    before = len(rows(api, BugActivity))
    response = api.get(state["url"] + "/options", headers=state["owner"])
    assert response.status_code == 200, response.text
    response, _ = result(
        api,
        state,
        claimed,
        "update_fields",
        permit,
        evidence=True,
        payload={"openedBuild": ["60", "61"], "assignedTo": "dev"},
    )
    assert response.status_code == 200, response.text
    assert len(rows(api, BugActivity)) == before
    original = next(
        step for step in rows(api, IntegrationJobStep) if step.operation_id == permit["operationId"]
    )
    assert original.result_json["openedBuild"] == ["61", "60"]


def test_attachment_reconcile_restores_only_its_original_step_and_mapping(
    api, integration, attachments
):
    state = integration
    file_id = seed(api, state)
    claimed = create_remote_mapping(api, state)
    permit, _ = prepare(
        api, state, claimed, "upload_attachment:" + file_id, {"remoteBugId": 50, "fileId": file_id}
    )
    assert permit.status_code == 200, permit.text
    response, _ = result(
        api,
        state,
        claimed,
        "upload_attachment:" + file_id,
        permit.json(),
        status="unknown",
        payload={"errorCode": "remote_uncertain"},
    )
    assert response.status_code == 200, response.text
    response = api.post(
        state["url"] + f"/attachments/{file_id}/reconcile",
        headers=state["owner"],
        json={"remoteFileId": 101},
    )
    assert response.status_code == 200, response.text
    attachment = rows(api, BugZentaoAttachment)[0]
    assert attachment.status == "succeeded" and attachment.remote_file_id == 101
    job = rows(api, IntegrationJob)[0]
    assert job.status == "partial"
    assert job.mapping_json["files"][file_id]["remoteFileId"] == 101
    assert rows(api, IntegrationJobStep)[1].operation_id == permit.json()["operationId"]
    assert state["uploads"] == []


@pytest.mark.parametrize("repair", [False, True])
def test_description_readback_or_bounded_repair_resolves_the_original_ledger(
    api,
    integration,
    attachments,
    repair,
):
    state = integration
    html = image(api, state)
    claimed = create_remote_mapping(api, state)
    upload, _ = prepare(
        api,
        state,
        claimed,
        "upload_attachment:inline-image",
        {"remoteBugId": 50, "fileId": "inline-image"},
    )
    response, _ = result(
        api,
        state,
        claimed,
        "upload_attachment:inline-image",
        upload.json(),
        payload={"remoteFileId": 101},
    )
    assert response.status_code == 200, response.text
    view, _ = context(api, state, claimed)
    desired = html.replace(
        '<img data-file-id="inline-image">', '<img src="http://zentao.test/file-read-101.png" >'
    )
    data = {
        "remoteBugId": 50,
        "beforeSteps": view["snapshot"]["createPayload"]["steps"],
        "desiredSteps": desired,
        "imagePaths": {"inline-image": "http://zentao.test/file-read-101.png"},
        "imageExtensions": {"inline-image": "png"},
    }
    description, _ = prepare(api, state, claimed, "update_description", data)
    assert description.status_code == 200, description.text
    response, _ = result(
        api,
        state,
        claimed,
        "update_description",
        description.json(),
        status="unknown",
        payload={"errorCode": "remote_uncertain"},
    )
    assert response.status_code == 200, response.text
    original_operation = description.json()["operationId"]
    before = desired
    if repair:
        # Seed a genuine historical legacy intent, rather than pass invalid legacy URLs
        # through today's stricter prepare validator.
        legacy = desired.replace("http://zentao.test/file-read-101.png", "{101.png}")
        row = rows(api, BugZentaoPush)[0]
        change(
            api,
            BugZentaoPush,
            "description_sync_json",
            {**row.description_sync_json, "desiredSteps": legacy},
            bug_id=state["bug"]["bugId"],
        )
        step = next(
            step for step in rows(api, IntegrationJobStep) if step.kind == "update_description"
        )
        changed = {**step.input_json, "desiredSteps": legacy}
        change(api, IntegrationJobStep, "input_json", changed, operation_id=original_operation)
        before = legacy.replace("{101.png}", "%7B101.png%7D")
    submit(api, state)
    new = claim(api, state)["job"]
    response, _ = prepare(
        api, state, new, "create_bug", {"result": {"remoteBugId": 50}}, decision="noop"
    )
    assert response.status_code == 200, response.text
    response, _ = prepare(
        api,
        state,
        new,
        "upload_attachment:inline-image",
        {"remoteBugId": 50, "fileId": "inline-image", "result": {"remoteFileId": 101}},
        decision="noop",
    )
    assert response.status_code == 200, response.text
    proof = (
        {**data, "beforeSteps": before}
        if repair
        else {
            "remoteBugId": 50,
            "beforeSteps": before,
            "result": {"descriptionHash": source_hash(desired)},
        }
    )
    response, _ = prepare(
        api, state, new, "update_description", proof, decision="write" if repair else "noop"
    )
    assert response.status_code == 200, response.text
    if repair:
        assert response.json()["writeAllowed"]
        confirmed, _ = result(
            api,
            state,
            new,
            "update_description",
            response.json(),
            payload={"descriptionHash": source_hash(desired)},
        )
        assert confirmed.status_code == 200, confirmed.text
    for job in rows(api, IntegrationJob):
        assert job.status == "succeeded"
    original = next(
        step for step in rows(api, IntegrationJobStep) if step.operation_id == original_operation
    )
    assert original.status == "succeeded"
    assert original.receipts_json[-1]["source"] == "readonly_recovery"
    assert rows(api, BugZentaoPush)[0].description_status == "succeeded"
    assert state["uploads"] == []


def test_confirmed_description_noop_does_not_recover_or_rewrite_old_receipts(
    api, integration, attachments
):
    state = integration
    source = image(api, state)
    claimed = create_remote_mapping(api, state)
    upload, _ = prepare(
        api,
        state,
        claimed,
        "upload_attachment:inline-image",
        {"remoteBugId": 50, "fileId": "inline-image"},
    )
    uploaded, _ = result(
        api,
        state,
        claimed,
        "upload_attachment:inline-image",
        upload.json(),
        payload={"remoteFileId": 101},
    )
    assert uploaded.status_code == 200, uploaded.text
    view, _ = context(api, state, claimed)
    desired = source.replace(
        '<img data-file-id="inline-image">', '<img src="http://zentao.test/file-read-101.png" >'
    )
    data = {
        "remoteBugId": 50,
        "beforeSteps": view["snapshot"]["createPayload"]["steps"],
        "desiredSteps": desired,
        "imagePaths": {"inline-image": "http://zentao.test/file-read-101.png"},
        "imageExtensions": {"inline-image": "png"},
    }
    permit, _ = prepare(api, state, claimed, "update_description", data)
    assert permit.status_code == 200, permit.text
    done, _ = result(
        api,
        state,
        claimed,
        "update_description",
        permit.json(),
        payload={"descriptionHash": source_hash(desired)},
    )
    assert done.status_code == 200, done.text
    original = next(s for s in rows(api, IntegrationJobStep) if s.kind == "update_description")
    original_receipts, original_result = original.receipts_json, original.result_json
    row = rows(api, BugZentaoPush)[0]
    equivalent = desired.replace('" >', '">')
    change(
        api,
        BugZentaoPush,
        "description_sync_json",
        {**row.description_sync_json, "desiredSteps": equivalent},
        bug_id=state["bug"]["bugId"],
    )
    for _ in range(2):
        submit(api, state)
        new = claim(api, state)["job"]
        for key, proof in (
            ("create_bug", {"result": {"remoteBugId": 50}}),
            (
                "upload_attachment:inline-image",
                {
                    "remoteBugId": 50,
                    "fileId": "inline-image",
                    "result": {"remoteFileId": 101},
                },
            ),
            (
                "update_description",
                {
                    **data,
                    "beforeSteps": equivalent,
                    "result": {"descriptionHash": source_hash(desired)},
                },
            ),
        ):
            response, _ = prepare(api, state, new, key, proof, decision="noop")
            assert response.status_code == 200, response.text
        assert (
            next(j for j in rows(api, IntegrationJob) if j.job_id == new["jobId"]).status
            == "succeeded"
        )
    old = next(s for s in rows(api, IntegrationJobStep) if s.id == original.id)
    assert old.receipts_json == original_receipts and old.result_json == original_result
    assert state["uploads"] == []
