import asyncio

from sqlalchemy import select
from support.perf_api import PERF_YAML, environment, worker_headers, worker_settings
from support.project_api import account, project
from support.project_api import api as api

from testing_agent.models.worker_task import WorkerTask


def _connection(api, headers, project_id):
    response = api.post(
        f"/v1/projects/{project_id}/monitoring-connections",
        headers=headers,
        json={
            "name": "prom",
            "remoteWriteUrl": "http://127.0.0.1:19090/api/v1/write",
            "remoteWriteAuth": {
                "type": "basic",
                "username": "writer",
                "password": "secret",
            },
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["hasRemoteWriteCredentials"] is True
    assert "password" not in response.text
    return data["connectionId"]


def _case(api, headers, project_id):
    response = api.post(
        f"/v1/projects/{project_id}/perf-cases",
        headers=headers,
        json={"name": "ping-case", "yaml": PERF_YAML},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_perf_run_claim_execute_and_complete(api):
    worker_settings(api)
    _, headers = account(api, "perf-owner")
    project_id = project(api, headers, "perf-project")
    environment_id = environment(api, headers, project_id)
    connection_id = _connection(api, headers, project_id)
    case = _case(api, headers, project_id)

    response = api.post(
        f"/v1/perf-cases/{case['caseId']}/runs",
        headers=headers,
        json={
            "environmentId": environment_id,
            "monitoringConnectionId": connection_id,
        },
    )
    assert response.status_code == 200, response.text
    run = response.json()["data"]
    run_id = run["runId"]
    assert run["status"] == "queued"

    async def queue_row():
        async with api.app.state.test_sessions() as session:
            return await session.scalar(
                select(WorkerTask).where(WorkerTask.domain == "perf", WorkerTask.run_id == run_id)
            )

    task = asyncio.run(queue_row())
    assert task is not None
    assert task.status == "pending"

    claim = api.post(
        "/internal/perf-worker/tasks/claim",
        headers=worker_headers(),
        json={"workerId": "worker-1"},
    )
    assert claim.status_code == 200, claim.text
    claim_data = claim.json()
    assert claim_data["runId"] == run_id
    assert claim_data["leaseSeconds"] == 60
    task_id = claim_data["taskId"]

    snapshot = api.get(
        f"/internal/perf-worker/tasks/{task_id}/snapshot",
        headers=worker_headers(),
        params={"workerId": "worker-1"},
    )
    assert snapshot.status_code == 200, snapshot.text
    spec = snapshot.json()["runSpec"]
    assert spec["runId"] == run_id
    assert spec["environment"]["baseUrl"] == "http://127.0.0.1:18080"
    assert spec["remoteWrite"]["auth"]["type"] == "basic"
    assert spec["remoteWrite"]["auth"]["password"] == "secret"

    started = api.post(
        f"/internal/perf-worker/tasks/{task_id}/started",
        headers=worker_headers(),
        json={"workerId": "worker-1", "startedAt": "2026-11-16T10:00:00Z"},
    )
    assert started.status_code == 204, started.text

    heartbeat = api.post(
        f"/internal/perf-worker/tasks/{task_id}/heartbeat",
        headers=worker_headers(),
        json={"workerId": "worker-1"},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["stopRequested"] is False
    assert heartbeat.json()["leaseSeconds"] == 60

    completed = api.post(
        f"/internal/perf-worker/tasks/{task_id}/completed",
        headers=worker_headers(),
        json={
            "workerId": "worker-1",
            "runId": run_id,
            "status": "completed",
            "outcome": "passed",
            "exitCode": 0,
            "startedAt": "2026-11-16T10:00:00Z",
            "finishedAt": "2026-11-16T10:00:01Z",
            "durationMs": 1000,
            "k6Version": "2.3.0",
            "templateVersion": "1.0.0",
            "scriptSha256": "a" * 64,
            "summary": {"metrics": {"http_reqs": {"values": {"count": 1}}}},
            "flags": [],
            "errorMessage": "",
            "logTail": "",
            "runner": {"hostname": "runner", "cpuCount": 8},
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "success"

    duplicate = api.post(
        f"/internal/perf-worker/tasks/{task_id}/completed",
        headers=worker_headers(),
        json={"workerId": "worker-1", "status": "failed", "outcome": "execution_error"},
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "success"

    detail = api.get(f"/v1/perf-runs/{run_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["status"] == "completed"
    assert data["outcome"] == "passed"
    assert data["summary"]["metrics"]["http_reqs"]["values"]["count"] == 1
    assert data["k6Version"] == "2.3.0"


def test_perf_worker_requires_its_own_token(api):
    worker_settings(api)

    missing = api.post(
        "/internal/perf-worker/tasks/claim",
        json={"workerId": "worker-1"},
    )
    wrong = api.post(
        "/internal/perf-worker/tasks/claim",
        headers={"X-Worker-Token": "regular-worker-token"},
        json={"workerId": "worker-1"},
    )

    assert missing.status_code == 401, missing.text
    assert wrong.status_code == 401, wrong.text


def test_stop_wins_over_late_completion(api):
    worker_settings(api)
    _, headers = account(api, "perf-stop-owner")
    project_id = project(api, headers, "perf-stop-project")
    environment_id = environment(api, headers, project_id)
    connection_id = _connection(api, headers, project_id)
    case = _case(api, headers, project_id)
    run = api.post(
        f"/v1/perf-cases/{case['caseId']}/runs",
        headers=headers,
        json={
            "environmentId": environment_id,
            "monitoringConnectionId": connection_id,
        },
    ).json()["data"]
    run_id = run["runId"]
    claim = api.post(
        "/internal/perf-worker/tasks/claim",
        headers=worker_headers(),
        json={"workerId": "worker-stop"},
    ).json()
    task_id = claim["taskId"]
    api.post(
        f"/internal/perf-worker/tasks/{task_id}/started",
        headers=worker_headers(),
        json={"workerId": "worker-stop", "startedAt": "2026-11-16T10:00:00Z"},
    )

    stopped = api.post(f"/v1/perf-runs/{run_id}/stop", headers=headers)
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["data"]["status"] == "stopping"

    heartbeat = api.post(
        f"/internal/perf-worker/tasks/{task_id}/heartbeat",
        headers=worker_headers(),
        json={"workerId": "worker-stop"},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["stopRequested"] is True

    completed = api.post(
        f"/internal/perf-worker/tasks/{task_id}/completed",
        headers=worker_headers(),
        json={
            "workerId": "worker-stop",
            "status": "completed",
            "outcome": "passed",
            "exitCode": 0,
            "startedAt": "2026-11-16T10:00:00Z",
            "finishedAt": "2026-11-16T10:00:05Z",
            "durationMs": 5000,
            "k6Version": "2.3.0",
            "summary": {},
            "flags": [],
            "errorMessage": "",
            "logTail": "",
            "runner": {"hostname": "runner", "cpuCount": 8},
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "canceled"

    detail = api.get(f"/v1/perf-runs/{run_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["status"] == "canceled"
    assert detail.json()["data"]["outcome"] == "stopped"


def test_perf_run_freezes_monitoring_snapshot_after_connection_changes(api):
    worker_settings(api)
    _, headers = account(api, "perf-snapshot-owner")
    project_id = project(api, headers, "perf-snapshot-project")
    environment_id = environment(api, headers, project_id)
    connection_id = _connection(api, headers, project_id)

    updated = api.patch(
        f"/v1/monitoring-connections/{connection_id}",
        headers=headers,
        json={
            "name": "prom-before-run",
            "remoteWriteUrl": "http://prom.before:19090/api/v1/write",
        },
    )
    assert updated.status_code == 200, updated.text

    case = _case(api, headers, project_id)
    created = api.post(
        f"/v1/perf-cases/{case['caseId']}/runs",
        headers=headers,
        json={
            "environmentId": environment_id,
            "monitoringConnectionId": connection_id,
        },
    )
    assert created.status_code == 200, created.text
    run_id = created.json()["data"]["runId"]

    renamed = api.patch(
        f"/v1/monitoring-connections/{connection_id}",
        headers=headers,
        json={
            "name": "prom-after-run",
            "remoteWriteUrl": "http://prom.after:19090/api/v1/write",
        },
    )
    assert renamed.status_code == 200, renamed.text
    deleted = api.delete(f"/v1/monitoring-connections/{connection_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    detail = api.get(f"/v1/perf-runs/{run_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    monitoring = detail.json()["data"]["monitoring"]
    assert monitoring == {
        "connectionId": connection_id,
        "name": "prom-before-run",
        "remoteWriteUrl": "http://prom.before:19090/api/v1/write",
    }
    assert "secret" not in detail.text
