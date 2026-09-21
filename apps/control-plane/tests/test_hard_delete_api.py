"""Child-first deletion through authenticated HTTP endpoints."""

import asyncio

import pytest
from test_project_membership_api import account, project, requirement
from test_project_membership_api import api as api


@pytest.mark.parametrize(
    "suite_path,suite_key,case_path,case_body",
    [
        ("function-test-suites", "suiteId", "function-test-cases", {"title": "case"}),
        ("ui-test-suites", "suiteId", "ui-test-cases", {"name": "case", "stepsJson": []}),
        (
            "api-collections",
            "collectionId",
            "api-cases",
            {"name": "case", "method": "GET", "urlTemplate": "/"},
        ),
    ],
)
def test_http_child_first_delete_and_recreate(api, suite_path, suite_key, case_path, case_body):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    create_url = f"/v1/requirements/{rid}/{suite_path}"
    created = api.post(create_url, headers=owner, json={"name": "suite"})
    assert created.status_code == 200, created.text
    sid = created.json()["data"][suite_key]
    suite_url = f"/v1/{suite_path}/{sid}"
    created = api.post(f"{suite_url}/cases", headers=owner, json=case_body)
    assert created.status_code == 200, created.text
    cid = created.json()["data"]["caseId"]
    blocked = api.delete(suite_url, headers=owner)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["data"]["blockers"][0]["count"] == 1
    assert api.delete(f"/v1/{case_path}/{cid}", headers=owner).status_code == 200
    assert api.delete(suite_url, headers=owner).status_code == 200
    assert api.get(suite_url, headers=owner).status_code == 404
    assert api.delete(suite_url, headers=owner).status_code == 404
    recreated = api.post(create_url, headers=owner, json={"name": "suite"})
    assert recreated.status_code == 200, recreated.text
    assert recreated.json()["data"][suite_key] != sid


def test_ai_run_delete_needs_write_and_refuses_running(api):
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    tid = api.post(
        f"/v1/projects/{pid}/api-case-generate-tasks",
        headers=owner,
        json={"name": "task", "requirementId": rid},
    ).json()["data"]["taskId"]
    response = api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
    )
    assert response.status_code == 200, response.text

    async def seed_runs():
        from testing_agent import models as m

        async with api.app.state.test_sessions() as session:
            for status in ("running", "success"):
                run_id = f"run-{status}"
                session.add(
                    m.AiGenerateTaskRun(
                        run_id=run_id, task_id=tid, trigger_user_id="owner", status=status
                    )
                )
                # 运行记录的投影要求至少有一个阶段行，否则读接口按不存在处理。
                session.add(
                    m.AiGenerateRunStage(
                        id=f"stage-{status}", run_id=run_id, stage="generate", stage_order=0
                    )
                )
            await session.commit()

    asyncio.run(seed_runs())
    running_url = "/v1/api-case-generate-task-runs/run-running"
    assert api.delete(running_url, headers=viewer).status_code == 403
    assert api.delete(running_url, headers=owner).status_code == 409

    done_url = "/v1/api-case-generate-task-runs/run-success"
    assert api.delete(done_url, headers=owner).status_code == 200
    assert api.get(done_url, headers=owner).status_code == 404
    assert api.delete(done_url, headers=owner).status_code == 404

    assert api.get(running_url, headers=owner).status_code == 200
    assert api.get(f"/v1/api-case-generate-tasks/{tid}", headers=owner).status_code == 200
    remaining = api.get(f"/v1/api-case-generate-tasks/{tid}/runs", headers=owner)
    assert remaining.json()["data"]["total"] == 1


def test_code_risk_task_can_be_deleted_before_requirement(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    response = api.post(
        f"/v1/projects/{pid}/code-risk-analysis-tasks",
        headers=owner,
        json={"name": "risk", "requirementId": rid},
    )
    assert response.status_code == 200, response.text
    tid = response.json()["data"]["taskId"]
    assert api.delete(f"/v1/requirements/{rid}", headers=owner).status_code == 409
    response = api.delete(f"/v1/code-risk-analysis-tasks/{tid}", headers=owner)
    assert response.status_code == 200, response.text
    assert api.delete(f"/v1/requirements/{rid}", headers=owner).status_code == 200


def test_deleting_running_case_rejects_late_worker_result(api):
    from testing_agent.api.deps import verify_worker_token

    _, owner = account(api, "owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    col = api.post(
        f"/v1/requirements/{rid}/api-collections", headers=owner, json={"name": "api"}
    ).json()["data"]["collectionId"]
    env = api.post(
        f"/v1/projects/{pid}/api-environments", headers=owner, json={"name": "env"}
    ).json()["data"]["environmentId"]
    cid = api.post(
        f"/v1/api-collections/{col}/cases",
        headers=owner,
        json={"name": "case", "method": "GET", "urlTemplate": "/"},
    ).json()["data"]["caseId"]
    response = api.post(f"/v1/api-cases/{cid}/run", headers=owner, json={"environmentId": env})
    assert response.status_code == 200, response.text
    run_id = response.json()["data"]["runId"]
    api.app.dependency_overrides[verify_worker_token] = lambda: None
    claimed = api.post("/internal/api-worker/tasks/claim", json={"workerId": "worker"})
    assert claimed.status_code == 200, claimed.text
    wid = claimed.json()["data"]["taskId"]
    assert api.delete(f"/v1/api-cases/{cid}", headers=owner).status_code == 200
    late = api.post(
        f"/internal/api-worker/tasks/{wid}/completed",
        json={"workerId": "worker", "status": "success", "response": {"statusCode": 200}},
    )
    assert late.status_code == 404, late.text
    assert api.get(f"/v1/api-case-runs/{run_id}", headers=owner).status_code == 404
    assert api.get(f"/v1/api-collections/{col}/cases", headers=owner).json()["data"]["total"] == 0


def test_account_deletion_removes_personal_credentials(api):
    import asyncio

    from sqlalchemy import func, select

    from testing_agent.models.integration_connection import IntegrationConnection

    user, headers = account(api, "user")

    async def credentials(*, create=False):
        async with api.app.state.test_sessions() as session:
            if create:
                session.add(
                    IntegrationConnection(
                        connection_id="personal",
                        user_id=user["userId"],
                        provider="llm",
                        name="personal",
                        secret_json={"apiKey": "secret"},
                    )
                )
                await session.commit()
            return await session.scalar(select(func.count()).select_from(IntegrationConnection))

    assert asyncio.run(credentials(create=True)) == 1
    response = api.delete("/v1/user", headers=headers)
    assert response.status_code == 200, response.text
    assert asyncio.run(credentials()) == 0
