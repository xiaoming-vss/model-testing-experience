"""Report generation and export through the unified attempt Worker protocol."""

import asyncio
from datetime import date

from support.function_case_library import make_sprint
from support.project_api import account, project
from support.project_api import api as api

from testing_agent.api.deps import verify_worker_token
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics


def test_report_worker_history_delete_and_pdf(api):
    _, owner = account(api, "report-owner")
    _, viewer = account(api, "report-viewer")
    _, stranger = account(api, "report-stranger")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "report-viewer", "role": "viewer"},
        ).status_code
        == 200
    )
    sprint_id = make_sprint(api, owner, pid)
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

    async def seed_metrics():
        async with api.app.state.test_sessions() as session:
            session.add(
                SprintDailyMetrics(
                    project_id=pid, sprint_id=sprint_id, snapshot_date=date(2026, 1, 15)
                )
            )
            await session.commit()

    asyncio.run(seed_metrics())
    api.app.dependency_overrides[verify_worker_token] = lambda: None
    run_url = f"/v1/projects/{pid}/test-report-generate-runs"

    def run(status):
        payload = {
            "sprintId": sprint_id,
            "connectionId": connection_id,
            "snapshotDate": "2026-01-15",
            "requestId": f"report-{status}",
        }
        response = api.post(
            run_url,
            headers=owner,
            json=payload,
        )
        assert response.status_code == 200, response.text
        execution_id = response.json()["data"]["runId"]
        replay = api.post(run_url, headers=owner, json=payload)
        assert replay.status_code == 200, replay.text
        assert replay.json()["data"]["runId"] == execution_id
        assert (
            api.post(
                run_url, headers=owner, json={**payload, "instruction": "different"}
            ).status_code
            == 400
        )
        path = f"/v1/test-report-generate-runs/{execution_id}"
        assert api.delete(path, headers=viewer).status_code == 403
        assert api.delete(path, headers=owner).status_code == 409
        claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "report-worker"})
        assert claim.status_code == 200, claim.text
        task_id, attempt_id = claim.json()["taskId"], claim.json()["attemptId"]
        assert attempt_id != execution_id
        base = f"/internal/ai-worker/tasks/{task_id}"
        assert api.get(f"{base}/snapshot").json()["run"]["dailyMetrics"]
        credentials = api.get(f"{base}/llm-credentials")
        assert credentials.status_code == 200
        assert credentials.json()["apiKey"] == "secret"
        assert (
            api.post(
                f"{base}/started", json={"workerId": "report-worker", "attemptId": attempt_id}
            ).status_code
            == 204
        )
        assert (
            api.patch(
                f"{base}/progress",
                json={
                    "workerId": "report-worker",
                    "attemptId": attempt_id,
                    "currentStage": "report_generating",
                    "stageStatus": "running",
                },
            ).status_code
            == 204
        )
        result = api.post(
            f"{base}/completed",
            json={
                "workerId": "report-worker",
                "attemptId": attempt_id,
                "status": status,
                "outputYaml": "# 测试报告\n\n已完成" if status == "success" else "",
                "errorMessage": "report failed" if status == "failed" else "",
            },
        )
        assert result.status_code == 204, result.text
        replay_finished = api.post(run_url, headers=owner, json=payload)
        assert replay_finished.status_code == 200, replay_finished.text
        assert replay_finished.json()["data"]["runId"] == execution_id
        assert replay_finished.json()["data"]["status"] == status
        return execution_id

    try:
        first, second = run("success"), run("failed")
        history = api.get(run_url, headers=owner, params={"sprintId": sprint_id})
        assert history.status_code == 200, history.text
        assert [row["runId"] for row in history.json()["data"]["items"]] == [second, first]
        assert history.json()["data"]["items"][0]["errorMessage"] == "report failed"
        pdf = api.get(f"/v1/test-report-generate-runs/{first}/pdf", headers=owner)
        assert pdf.status_code == 200, pdf.text
        assert pdf.content.startswith(b"%PDF")
        assert api.get(
            f"/v1/test-report-generate-runs/{first}/pdf", headers=stranger
        ).status_code in (403, 404)
        assert (
            api.delete(f"/v1/test-report-generate-runs/{second}", headers=owner).status_code == 200
        )
        detail = api.get(f"/v1/test-report-generate-runs/{first}", headers=owner)
        assert detail.json()["data"]["resultYaml"].startswith("# 测试报告")
    finally:
        api.app.dependency_overrides.pop(verify_worker_token, None)
