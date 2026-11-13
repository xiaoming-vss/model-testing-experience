"""Code-risk runs expose execution IDs while Workers use attempt IDs."""

from unittest.mock import AsyncMock

from support.project_api import account, project, requirement
from support.project_api import api as api
from support.requirement_versions import approve_material

from testing_agent.api.deps import verify_worker_token
from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService


def test_code_risk_worker_result_history_and_delete(api, monkeypatch):
    _, owner = account(api, "risk-owner")
    _, viewer = account(api, "risk-viewer")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "risk-viewer", "role": "viewer"},
        ).status_code
        == 200
    )
    requirement_id = requirement(api, owner, pid)
    material_id = approve_material(api, requirement_id)
    connection = api.post(
        f"/v1/projects/{pid}/integrations/llm/connections",
        headers=owner,
        json={
            "name": "llm",
            "baseUrl": "https://llm.example/v1",
            "apiKey": "secret",
            "modelId": "model",
        },
    )
    assert connection.status_code == 200, connection.text
    connection_id = connection.json()["data"]["connectionId"]
    task = api.post(
        f"/v1/projects/{pid}/code-risk-analysis-tasks",
        headers=owner,
        json={"name": "风险", "requirementId": requirement_id},
    )
    assert task.status_code == 200, task.text
    task_id = task.json()["data"]["taskId"]

    async def snapshot(
        task, run_id, worker_task_id, instruction, *, user_id, connection_ids, **kwargs
    ):
        return {
            "taskId": task.task_id,
            "runId": run_id,
            "requirement": {"name": "需求"},
            "requirementMaterialVersion": {"versionId": material_id, "versionNo": 1},
            "bindings": [],
            "existingTests": {},
        }

    build_snapshot = AsyncMock(side_effect=snapshot)
    monkeypatch.setattr(CodeRiskAnalysisService, "build_snapshot", build_snapshot)
    api.app.dependency_overrides[verify_worker_token] = lambda: None

    def execute(status):
        payload = {"connectionId": connection_id, "requestId": f"risk-{status}"}
        response = api.post(
            f"/v1/code-risk-analysis-tasks/{task_id}/run",
            headers=owner,
            json=payload,
        )
        assert response.status_code == 200, response.text
        execution_id = response.json()["data"]["runId"]
        snapshot_calls = build_snapshot.await_count
        replay = api.post(
            f"/v1/code-risk-analysis-tasks/{task_id}/run", headers=owner, json=payload
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["data"]["runId"] == execution_id
        assert build_snapshot.await_count == snapshot_calls
        mismatch = api.post(
            f"/v1/code-risk-analysis-tasks/{task_id}/run",
            headers=owner,
            json={**payload, "instruction": "different"},
        )
        assert mismatch.status_code == 400
        assert (
            api.delete(f"/v1/code-risk-analysis-runs/{execution_id}", headers=viewer).status_code
            == 403
        )
        assert (
            api.delete(f"/v1/code-risk-analysis-runs/{execution_id}", headers=owner).status_code
            == 409
        )
        assert (
            api.delete(f"/v1/code-risk-analysis-tasks/{task_id}", headers=owner).status_code == 409
        )
        claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "risk-worker"})
        assert claim.status_code == 200, claim.text
        queue_id, attempt_id = claim.json()["taskId"], claim.json()["attemptId"]
        assert queue_id == payload["requestId"]
        assert build_snapshot.await_args.args[2] == queue_id
        assert execution_id != attempt_id
        base = f"/internal/ai-worker/tasks/{queue_id}"
        assert api.get(f"{base}/snapshot").json()["run"]["attemptId"] == attempt_id
        credentials = api.get(f"{base}/llm-credentials")
        assert credentials.status_code == 200
        assert credentials.json()["apiKey"] == "secret"
        assert (
            api.post(
                f"{base}/started", json={"workerId": "risk-worker", "attemptId": attempt_id}
            ).status_code
            == 204
        )
        assert (
            api.patch(
                f"{base}/progress",
                json={
                    "workerId": "risk-worker",
                    "attemptId": attempt_id,
                    "currentStage": "fetching_diff",
                    "stageStatus": "running",
                },
            ).status_code
            == 204
        )
        complete = api.post(
            f"{base}/completed",
            json={
                "workerId": "risk-worker",
                "attemptId": attempt_id,
                "status": status,
                "resultYaml": "risks:\n  - reason: changed" if status == "success" else "",
                "errorMessage": "risk failed" if status == "failed" else "",
            },
        )
        assert complete.status_code == 204, complete.text
        replay_finished = api.post(
            f"/v1/code-risk-analysis-tasks/{task_id}/run", headers=owner, json=payload
        )
        assert replay_finished.status_code == 200, replay_finished.text
        assert replay_finished.json()["data"]["runId"] == execution_id
        assert replay_finished.json()["data"]["status"] == status
        return execution_id

    try:
        first, second = execute("success"), execute("failed")
        history = api.get(f"/v1/code-risk-analysis-tasks/{task_id}/runs", headers=owner)
        assert history.status_code == 200, history.text
        assert [item["runId"] for item in history.json()["data"]["items"]] == [second, first]
        assert history.json()["data"]["items"][0]["errorMessage"] == "risk failed"
        detail = api.get(f"/v1/code-risk-analysis-runs/{first}", headers=owner)
        assert detail.json()["data"]["report"]["risks"][0]["reason"] == "changed"
        assert api.delete(f"/v1/code-risk-analysis-runs/{second}", headers=owner).status_code == 200
        assert api.get(f"/v1/code-risk-analysis-runs/{first}", headers=owner).status_code == 200
    finally:
        api.app.dependency_overrides.pop(verify_worker_token, None)
