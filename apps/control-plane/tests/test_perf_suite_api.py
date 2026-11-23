import asyncio
from dataclasses import replace

from sqlalchemy import func, select
from support.project_api import account, project
from support.project_api import api as api  # noqa: F401

from testing_agent.core.config import get_settings
from testing_agent.models.worker_task import WorkerTask

_PERF_YAML = """
specVersion: "1.0"
case:
  name: ping
  steps:
    - name: ping
      method: GET
      path: /ping
      checks:
        - type: status
          op: eq
          value: 200
  load:
    model: vus
    vus: 1
    duration: "1s"
  acceptance:
    source: user_confirmed
    confirmed: true
    criteria:
      http_req_failed: ["rate<0.01"]
"""

_WORKER_HEADERS = {"X-Worker-Token": "perf-worker-token"}


def _settings(api):
    settings = replace(
        get_settings(),
        integration_key="test-integration-key",
        perf_worker_key="perf-worker-token",
    )
    api.app.dependency_overrides[get_settings] = lambda: settings
    return settings


def _environment(api, headers, project_id, name="perf-env"):
    response = api.post(
        f"/v1/projects/{project_id}/api-environments",
        headers=headers,
        json={
            "name": name,
            "kind": "perf",
            "baseUrl": "http://127.0.0.1:18080",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["environmentId"]


def _connection(api, headers, project_id, name="prom"):
    response = api.post(
        f"/v1/projects/{project_id}/monitoring-connections",
        headers=headers,
        json={
            "name": name,
            "remoteWriteUrl": "http://127.0.0.1:19090/api/v1/write",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["connectionId"]


def _suite(api, headers, project_id, name="suite"):
    response = api.post(
        f"/v1/projects/{project_id}/perf-suites",
        headers=headers,
        json={"name": name, "description": "serial suite"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _case(api, headers, project_id, suite_id, name="case-a"):
    response = api.post(
        f"/v1/projects/{project_id}/perf-cases",
        headers=headers,
        json={"name": name, "yaml": _PERF_YAML, "suiteId": suite_id},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _run_suite(api, headers, suite_id, environment_id, connection_id):
    suite = api.get(f"/v1/perf-suites/{suite_id}", headers=headers).json()["data"]
    sprint = api.post(
        f"/v1/projects/{suite['projectId']}/sprints",
        headers=headers,
        json={
            "name": "perf-sprint",
            "startTime": "2026-10-01T00:00:00Z",
            "endTime": "2026-11-01T00:00:00Z",
        },
    )
    assert sprint.status_code == 200, sprint.text
    sprint_id = sprint.json()["data"]["sprintId"]
    response = api.post(
        f"/v1/perf-suites/{suite_id}/runs",
        headers=headers,
        json={
            "environmentId": environment_id,
            "monitoringConnectionId": connection_id,
            "sprintId": sprint_id,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["sprintId"] == sprint_id
    return response.json()["data"]


def _claim(api, worker_id="worker-suite"):
    response = api.post(
        "/internal/perf-worker/tasks/claim",
        headers=_WORKER_HEADERS,
        json={"workerId": worker_id},
    )
    if response.status_code == 204:
        return None
    assert response.status_code == 200, response.text
    return response.json()


def _start(api, task_id, worker_id="worker-suite"):
    response = api.post(
        f"/internal/perf-worker/tasks/{task_id}/started",
        headers=_WORKER_HEADERS,
        json={"workerId": worker_id, "startedAt": "2026-11-17T10:00:00Z"},
    )
    assert response.status_code == 204, response.text


def _complete(api, task_id, run_id, *, status="completed", worker_id="worker-suite"):
    response = api.post(
        f"/internal/perf-worker/tasks/{task_id}/completed",
        headers=_WORKER_HEADERS,
        json={
            "workerId": worker_id,
            "runId": run_id,
            "status": status,
            "outcome": "inconclusive" if status == "completed" else "execution_error",
            "exitCode": 0,
            "startedAt": "2026-11-17T10:00:00Z",
            "finishedAt": "2026-11-17T10:00:01Z",
            "durationMs": 1000,
            "summary": {},
            "flags": [],
            "errorMessage": "",
            "logTail": "",
            "runner": {"hostname": "runner"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _pending_tasks(api, run_ids):
    async def count():
        async with api.app.state.test_sessions() as session:
            return await session.scalar(
                select(func.count())
                .select_from(WorkerTask)
                .where(
                    WorkerTask.domain == "perf",
                    WorkerTask.run_id.in_(run_ids),
                    WorkerTask.status == "pending",
                )
            )

    return asyncio.run(count())


def _setup(api, prefix):
    _settings(api)
    _, headers = account(api, prefix)
    project_id = project(api, headers, f"{prefix}-project")
    environment_id = _environment(api, headers, project_id)
    connection_id = _connection(api, headers, project_id)
    suite = _suite(api, headers, project_id, f"{prefix}-suite")
    first = _case(api, headers, project_id, suite["suiteId"], "case-a")
    second = _case(api, headers, project_id, suite["suiteId"], "case-b")
    return headers, suite, first, second, environment_id, connection_id


def test_perf_suite_crud_and_case_order(api):
    _settings(api)
    _, headers = account(api, "suite-owner")
    project_id = project(api, headers, "suite-project")
    suite = _suite(api, headers, project_id)
    first = _case(api, headers, project_id, suite["suiteId"], "first")
    second = _case(api, headers, project_id, suite["suiteId"], "second")

    detail = api.get(f"/v1/perf-suites/{suite['suiteId']}", headers=headers)
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert [item["name"] for item in data["cases"]] == ["first", "second"]
    assert [item["orderNo"] for item in data["cases"]] == [1, 2]
    assert data["caseCount"] == 2

    reordered = api.put(
        f"/v1/perf-suites/{suite['suiteId']}/case-order",
        headers=headers,
        json={"caseIds": [second["caseId"], first["caseId"]]},
    )
    assert reordered.status_code == 200, reordered.text
    assert [item["name"] for item in reordered.json()["data"]["cases"]] == ["second", "first"]
    assert [item["orderNo"] for item in reordered.json()["data"]["cases"]] == [1, 2]

    invalid = api.put(
        f"/v1/perf-suites/{suite['suiteId']}/case-order",
        headers=headers,
        json={"caseIds": [first["caseId"]]},
    )
    assert invalid.status_code == 400, invalid.text

    listed = api.get(f"/v1/projects/{project_id}/perf-suites", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["items"][0]["caseCount"] == 2


def test_suite_run_requires_sprint_from_same_project(api):
    headers, suite, _, _, environment_id, connection_id = _setup(api, "suite-sprint")
    path = f"/v1/perf-suites/{suite['suiteId']}/runs"
    body = {"environmentId": environment_id, "monitoringConnectionId": connection_id}
    assert api.post(path, headers=headers, json=body).status_code == 400
    other = project(api, headers, "other-project")
    sprint = api.post(
        f"/v1/projects/{other}/sprints",
        headers=headers,
        json={
            "name": "other",
            "startTime": "2026-10-01T00:00:00Z",
            "endTime": "2026-11-01T00:00:00Z",
        },
    )
    assert sprint.status_code == 200
    body["sprintId"] = sprint.json()["data"]["sprintId"]
    assert api.post(path, headers=headers, json=body).status_code == 400


def test_perf_suite_runs_cases_serially(api):
    headers, suite, _first, _second, environment_id, connection_id = _setup(api, "suite-serial")

    run = _run_suite(api, headers, suite["suiteId"], environment_id, connection_id)
    suite_run_id = run["suiteRunId"]
    assert run["status"] == "running"
    assert run["totalCount"] == 2
    assert [item["status"] for item in run["items"]] == ["queued", "pending"]
    child_ids = [item["childRunId"] for item in run["items"]]
    assert _pending_tasks(api, child_ids) == 1

    first_task = _claim(api)
    assert first_task["runId"] == child_ids[0]
    snapshot = api.get(
        f"/internal/perf-worker/tasks/{first_task['taskId']}/snapshot",
        headers=_WORKER_HEADERS,
        params={"workerId": "worker-suite"},
    )
    assert snapshot.status_code == 200, snapshot.text
    spec = snapshot.json()["runSpec"]
    assert spec["projectId"] == suite["projectId"]
    assert spec["sprintId"] == run["sprintId"]
    assert spec["suiteId"] == suite["suiteId"]
    assert spec["suiteRunId"] == suite_run_id
    assert spec["caseId"] == _first["caseId"]
    _start(api, first_task["taskId"])
    _complete(api, first_task["taskId"], child_ids[0])

    detail = api.get(f"/v1/perf-suite-runs/{suite_run_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["status"] == "running"
    assert data["completedCount"] == 1
    assert [item["status"] for item in data["items"]] == ["completed", "queued"]
    assert _pending_tasks(api, child_ids) == 1

    second_task = _claim(api)
    assert second_task["runId"] == child_ids[1]
    assert _claim(api) is None
    _start(api, second_task["taskId"])
    _complete(api, second_task["taskId"], child_ids[1])

    detail = api.get(f"/v1/perf-suite-runs/{suite_run_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["status"] == "completed"
    assert data["outcome"] == "inconclusive"
    assert data["completedCount"] == 2
    assert data["failedCount"] == 0
    assert [item["status"] for item in data["items"]] == ["completed", "completed"]

    listed = api.get(
        f"/v1/projects/{suite['projectId']}/perf-suite-runs",
        headers=headers,
        params={"suiteId": suite["suiteId"]},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["total"] == 1


def test_perf_suite_continues_after_case_failure(api):
    headers, suite, _first, _second, environment_id, connection_id = _setup(api, "suite-fail")
    run = _run_suite(api, headers, suite["suiteId"], environment_id, connection_id)
    child_ids = [item["childRunId"] for item in run["items"]]

    first_task = _claim(api)
    _start(api, first_task["taskId"])
    _complete(api, first_task["taskId"], child_ids[0], status="failed")

    detail = api.get(f"/v1/perf-suite-runs/{run['suiteRunId']}", headers=headers).json()["data"]
    assert detail["status"] == "running"
    assert detail["failedCount"] == 1
    assert [item["status"] for item in detail["items"]] == ["failed", "queued"]

    second_task = _claim(api)
    _start(api, second_task["taskId"])
    _complete(api, second_task["taskId"], child_ids[1])

    detail = api.get(f"/v1/perf-suite-runs/{run['suiteRunId']}", headers=headers).json()["data"]
    assert detail["status"] == "completed"
    assert detail["outcome"] == "inconclusive"
    assert detail["failedCount"] == 1
    assert detail["completedCount"] == 1


def test_perf_suite_stop_skips_remaining_cases(api):
    headers, suite, _first, _second, environment_id, connection_id = _setup(api, "suite-stop")
    run = _run_suite(api, headers, suite["suiteId"], environment_id, connection_id)
    child_ids = [item["childRunId"] for item in run["items"]]

    first_task = _claim(api)
    _start(api, first_task["taskId"])
    stopped = api.post(f"/v1/perf-suite-runs/{run['suiteRunId']}/stop", headers=headers)
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["data"]["status"] == "stopping"

    heartbeat = api.post(
        f"/internal/perf-worker/tasks/{first_task['taskId']}/heartbeat",
        headers=_WORKER_HEADERS,
        json={"workerId": "worker-suite"},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["stopRequested"] is True

    _complete(api, first_task["taskId"], child_ids[0])

    detail = api.get(f"/v1/perf-suite-runs/{run['suiteRunId']}", headers=headers).json()["data"]
    assert detail["status"] == "canceled"
    assert detail["outcome"] == "stopped"
    assert detail["completedCount"] == 0
    assert detail["skippedCount"] == 1
    assert [item["status"] for item in detail["items"]] == ["canceled", "skipped"]
    assert _pending_tasks(api, child_ids) == 0


def test_stopping_child_run_cascades_to_suite(api):
    headers, suite, _first, _second, environment_id, connection_id = _setup(api, "suite-child-stop")
    run = _run_suite(api, headers, suite["suiteId"], environment_id, connection_id)
    child_ids = [item["childRunId"] for item in run["items"]]

    stopped = api.post(f"/v1/perf-runs/{child_ids[0]}/stop", headers=headers)
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["data"]["status"] == "canceled"

    detail = api.get(f"/v1/perf-suite-runs/{run['suiteRunId']}", headers=headers).json()["data"]
    assert detail["status"] == "canceled"
    assert detail["outcome"] == "stopped"
    assert [item["status"] for item in detail["items"]] == ["canceled", "skipped"]
    assert _pending_tasks(api, child_ids) == 0


def test_deleting_suite_cascades_cases_and_run_history(api):
    headers, suite, first, _second, environment_id, connection_id = _setup(api, "suite-delete")
    run = _run_suite(api, headers, suite["suiteId"], environment_id, connection_id)
    child_ids = [item["childRunId"] for item in run["items"]]
    first_task = _claim(api)
    _start(api, first_task["taskId"])
    _complete(api, first_task["taskId"], child_ids[0])

    deleted = api.delete(f"/v1/perf-suites/{suite['suiteId']}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert api.get(f"/v1/perf-suites/{suite['suiteId']}", headers=headers).status_code == 404
    assert api.get(f"/v1/perf-cases/{first['caseId']}", headers=headers).status_code == 404
    assert api.get(f"/v1/perf-suite-runs/{run['suiteRunId']}", headers=headers).status_code == 404
    assert api.get(f"/v1/perf-runs/{child_ids[0]}", headers=headers).status_code == 404
    assert _pending_tasks(api, child_ids) == 0


def test_project_deletion_requires_removing_perf_suites(api):
    _settings(api)
    _, headers = account(api, "suite-project-delete")
    project_id = project(api, headers, "suite-project-delete-project")
    suite = _suite(api, headers, project_id, "delete-blocker-suite")

    blocked = api.delete(f"/v1/projects/{project_id}", headers=headers)
    assert blocked.status_code == 409, blocked.text
    blockers = {item["resource"]: item["count"] for item in blocked.json()["data"]["blockers"]}
    assert blockers.get("perf_suites") == 1

    assert api.delete(f"/v1/perf-suites/{suite['suiteId']}", headers=headers).status_code == 200
    assert api.delete(f"/v1/projects/{project_id}", headers=headers).status_code == 200
