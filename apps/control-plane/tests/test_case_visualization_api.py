import copy
import json
from pathlib import Path

from sqlalchemy import select
from support.case_visualization import make_llm, order_fixture, query
from support.function_case_library import make_case, make_requirement, make_suite
from support.order_api import entries_of
from support.project_api import api as api

from testing_agent.api.deps import verify_worker_token
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.worker_task import WorkerTask

EXAMPLE = json.loads(
    (
        Path(__file__).parents[1]
        / "default-skills/mtx-analyze-case-visualization/references/examples.json"
    ).read_text()
)[0]


def setup(api):
    owner, pid, sprint, order = order_fixture(api)
    req = make_requirement(api, owner, sprint)
    suite = make_suite(api, owner, req)
    case = make_case(api, owner, suite, content=EXAMPLE["input"]["content"])
    assert (
        api.post(
            f"/v1/test-orders/{order}/cases", headers=owner, json={"caseIds": [case]}
        ).status_code
        == 200
    )
    entry = entries_of(api, owner, order)["items"][0]["entryId"]
    conn = make_llm(api, owner, pid)
    api.app.dependency_overrides[verify_worker_token] = lambda: None
    return owner, order, entry, conn, case


def submit(api, owner, order, entry, conn, req="request-1", mode="generate"):
    return api.post(
        f"/v1/test-orders/{order}/entries/{entry}/visualization/runs",
        headers=owner,
        json={"requestId": req, "connectionId": conn, "mode": mode},
    )


def view(api, owner, order, entry):
    response = api.get(f"/v1/test-orders/{order}/entries/{entry}/visualization", headers=owner)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def finish(api, entry, *, artifact_status="ready", invalid=False, failed=False):
    claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"})
    assert claim.status_code == 200, claim.text
    task = claim.json()
    base = f"/internal/ai-worker/tasks/{task['taskId']}"
    snapshot = api.get(base + "/snapshot")
    assert snapshot.status_code == 200, snapshot.text
    frozen = json.loads(snapshot.json()["configJson"])["visualizationInput"]
    output = copy.deepcopy(EXAMPLE["output"])
    output["executionEntryId"] = entry
    assert output["sources"] == frozen["sources"]
    output["status"] = artifact_status
    if artifact_status == "unsupported":
        output["visuals"] = []
        output["limitations"] = [{"reason": "暂不适合图解", "sourceIds": ["e0"]}]
    if artifact_status == "partial":
        output["limitations"] = [{"reason": "部分内容未覆盖", "sourceIds": ["a0"]}]
    if invalid:
        output["executionEntryId"] = "other"
    assert (
        api.post(
            base + "/started", json={"workerId": "worker", "attemptId": task["attemptId"]}
        ).status_code
        == 204
    )
    body = {
        "workerId": "worker",
        "attemptId": task["attemptId"],
        "status": "failed" if failed else "success",
        "resultYaml": json.dumps(output),
        "resultSummaryJson": {"visualization": {"skillDigest": "a" * 64, "model": "test"}},
    }
    response = api.post(base + "/completed", json=body)
    assert response.status_code == 204, response.text
    return base, body


def test_single_lifecycle_keeps_effective_and_idempotency(api):
    owner, order, entry, conn, _ = setup(api)
    assert view(api, owner, order, entry)["effectiveArtifact"] is None
    first = submit(api, owner, order, entry, conn)
    assert first.status_code == 200, first.text
    assert (
        submit(api, owner, order, entry, conn).json()["data"]["runId"]
        == first.json()["data"]["runId"]
    )
    assert submit(api, owner, order, entry, conn, mode="regenerate").status_code == 400
    active = submit(api, owner, order, entry, conn, "other")
    assert active.json()["data"]["disposition"] == "existing_active"
    base, body = finish(api, entry, artifact_status="partial")
    previous = view(api, owner, order, entry)["effectiveArtifact"]
    assert previous["status"] == "partial"
    assert api.post(base + "/completed", json=body).status_code == 204
    assert (
        submit(api, owner, order, entry, conn, "skip").json()["data"]["disposition"]
        == "skipped_available"
    )
    for index, kwargs in enumerate(
        [{"failed": True}, {"artifact_status": "unsupported"}, {"invalid": True}]
    ):
        response = submit(api, owner, order, entry, conn, f"regen-{index}", "regenerate")
        assert response.status_code == 200, response.text
        assert (
            view(api, owner, order, entry)["effectiveArtifact"]["artifactId"]
            == previous["artifactId"]
        )
        finish(api, entry, **kwargs)
        current = view(api, owner, order, entry)
        assert current["effectiveArtifact"]["artifactId"] == previous["artifactId"]
        assert current["latestRun"]["status"] in {"failed", "success"}


def test_batch_partial_replay_and_skip(api):
    owner, order, entry, conn, _ = setup(api)
    body = {"requestId": "batch-1", "connectionId": conn, "entryIds": [entry, "not-found"]}
    url = f"/v1/test-orders/{order}/visualization-batches"
    first = api.post(url, headers=owner, json=body)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["counts"] == {"pending": 1, "rejected": 1}
    second = api.post(url, headers=owner, json=body)
    assert second.json()["data"]["batchId"] == data["batchId"]
    assert api.post(url, headers=owner, json={**body, "entryIds": [entry]}).status_code == 400
    finish(api, entry)
    result = api.get(url + "/" + data["batchId"], headers=owner).json()["data"]
    assert result["counts"] == {"ready": 1, "rejected": 1}
    skip = api.post(
        url, headers=owner, json={**body, "requestId": "batch-2", "entryIds": [entry]}
    ).json()["data"]
    assert skip["counts"] == {"skipped_available": 1}


def test_delete_entry_cleans_task_queue_and_rejects_late_result(api):
    owner, order, entry, conn, _ = setup(api)
    assert submit(api, owner, order, entry, conn).status_code == 200
    claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"}).json()
    assert api.delete(f"/v1/test-orders/{order}/entries/{entry}", headers=owner).status_code == 200
    assert not query(
        api,
        select(AiGenerateTask).where(AiGenerateTask.task_type == "test_order_case_visualization"),
    )
    assert not query(
        api, select(WorkerTask).where(WorkerTask.task_type == "test_order_case_visualization")
    )
    assert api.post(
        f"/internal/ai-worker/tasks/{claim['taskId']}/completed",
        json={
            "workerId": "worker",
            "attemptId": claim["attemptId"],
            "status": "success",
            "resultYaml": "{}",
        },
    ).status_code in {403, 404}


def test_cross_order_identity_and_input_injection_rejected(api):
    owner, order, entry, conn, _ = setup(api)
    assert submit(api, owner, order, "unknown", conn).status_code == 404
    assert (
        api.post(
            f"/v1/test-orders/{order}/entries/{entry}/visualization/runs",
            headers=owner,
            json={"requestId": "x", "connectionId": conn, "content": {}},
        ).status_code
        == 400
    )
    assert (
        api.post(
            f"/v1/test-orders/{order}/visualization-batches",
            headers=owner,
            json={"requestId": "x", "connectionId": conn, "entryIds": [str(i) for i in range(101)]},
        ).status_code
        == 400
    )


def test_viewer_can_read_but_cannot_generate_or_reuse_owner_credentials(api):
    from support.project_api import account

    owner, order, entry, conn, _ = setup(api)
    pid = api.get(f"/v1/test-orders/{order}", headers=owner).json()["data"]["projectId"]
    _, viewer = account(api, "viz-viewer")
    _, stranger = account(api, "viz-stranger")
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "viz-viewer", "role": "viewer"},
        ).status_code
        == 200
    )
    assert view(api, viewer, order, entry)["effectiveArtifact"] is None
    assert submit(api, viewer, order, entry, conn).status_code == 403
    assert api.get(
        f"/v1/test-orders/{order}/entries/{entry}/visualization", headers=stranger
    ).status_code in {403, 404}
    _, member = account(api, "viz-member")
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "viz-member", "role": "member"},
        ).status_code
        == 200
    )
    assert submit(api, member, order, entry, conn).status_code in {403, 404}


def test_order_and_source_case_deletion_clean_visualizations(api):
    owner, order, entry, conn, case = setup(api)
    assert submit(api, owner, order, entry, conn).status_code == 200
    finish(api, entry)
    response = api.delete(f"/v1/function-test-cases/{case}", headers=owner)
    assert response.status_code == 200, response.text
    assert not query(
        api,
        select(AiGenerateTask).where(AiGenerateTask.task_type == "test_order_case_visualization"),
    )
    assert api.delete(f"/v1/test-orders/{order}", headers=owner).status_code == 200


def test_snapshot_changes_hide_old_artifact_and_summary_has_no_body(api):
    import asyncio

    from testing_agent.models.test_order_entry import TestOrderEntry

    owner, order, entry, conn, _ = setup(api)
    assert submit(api, owner, order, entry, conn).status_code == 200
    finish(api, entry)
    summary = api.post(
        f"/v1/test-orders/{order}/visualizations/lookup", headers=owner, json={"entryIds": [entry]}
    ).json()["data"]["items"][0]
    assert summary["effectiveArtifact"]["content"] is None

    async def mutate_snapshot():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(
                select(TestOrderEntry).where(TestOrderEntry.entry_id == entry)
            )
            row.snapshot_json = {
                "preconditions": [],
                "steps": [{"action": "changed", "expected": "changed"}],
            }
            await session.commit()

    asyncio.run(mutate_snapshot())
    assert view(api, owner, order, entry)["effectiveArtifact"] is None


def test_role_revocation_retires_running_visualization(api):
    from support.project_api import account

    owner, order, entry, _, _ = setup(api)
    pid = api.get(f"/v1/test-orders/{order}", headers=owner).json()["data"]["projectId"]
    user, member = account(api, "viz-revoked")
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "viz-revoked", "role": "member"},
        ).status_code
        == 200
    )
    connection = make_llm(api, member, pid)
    assert submit(api, member, order, entry, connection).status_code == 200
    claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"}).json()
    assert (
        api.patch(
            f"/v1/projects/{pid}/members/{user['userId']}", headers=owner, json={"role": "viewer"}
        ).status_code
        == 200
    )
    response = api.get(f"/internal/ai-worker/tasks/{claim['taskId']}/snapshot")
    assert response.status_code == 403
    current = view(api, owner, order, entry)
    assert current["effectiveArtifact"] is None
    assert current["latestRun"]["status"] == "failed"


def test_safe_worker_failure_reason_is_shown_and_untrusted_reason_is_not(api):
    owner, order, entry, conn, _ = setup(api)
    safe = "图解结果校验失败：状态保持时前后状态必须使用同一实体，请重新生成"
    for index, supplied in enumerate([safe, "SECRET example untrusted error"]):
        assert submit(api, owner, order, entry, conn, f"reason-{index}").status_code == 200
        claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"}).json()
        base = f"/internal/ai-worker/tasks/{claim['taskId']}"
        assert (
            api.post(
                base + "/started", json={"workerId": "worker", "attemptId": claim["attemptId"]}
            ).status_code
            == 204
        )
        assert (
            api.post(
                base + "/completed",
                json={
                    "workerId": "worker",
                    "attemptId": claim["attemptId"],
                    "status": "failed",
                    "errorMessage": supplied,
                },
            ).status_code
            == 204
        )
        reason = view(api, owner, order, entry)["latestRun"]["errorMessage"]
        assert reason == (safe if index == 0 else "图解生成失败，请重试或继续使用文字模式")
