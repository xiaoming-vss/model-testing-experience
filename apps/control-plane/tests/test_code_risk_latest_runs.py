"""项目级代码风险任务最新运行：一次请求代替按任务扇出。"""

import asyncio

from support.project_api import account, api, project, requirement  # noqa: F401

from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage


def _create_task(client, headers, project_id, requirement_id, name):
    response = client.post(
        f"/v1/projects/{project_id}/code-risk-analysis-tasks",
        headers=headers,
        json={"name": name, "requirementId": requirement_id},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["taskId"]


def _seed_runs(client, user_id, task_id, stage_id):
    async def seed():
        async with client.app.state.test_sessions() as session:
            session.add(AiGenerationStage(id=stage_id, task_id=task_id, stage="generate"))
            session.add_all(
                [
                    AiExecution(
                        execution_id="exec-a",
                        task_id=task_id,
                        requested_by=user_id,
                    ),
                    AiExecution(
                        execution_id="exec-b",
                        task_id=task_id,
                        requested_by=user_id,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    AiGenerationAttempt(
                        id="attempt-a",
                        stage_id=stage_id,
                        execution_id="exec-a",
                        attempt_no=1,
                        operation="generate",
                        status="failed",
                        output_content="",
                    ),
                    AiGenerationAttempt(
                        id="attempt-b",
                        stage_id=stage_id,
                        execution_id="exec-b",
                        attempt_no=2,
                        operation="generate",
                        status="success",
                        output_content="risks: []",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(seed())


def test_latest_runs_return_one_summary_per_task(api):  # noqa: F811
    user, owner = account(api, "owner")
    pid = project(api, owner)
    requirement_id = requirement(api, owner, pid)
    first = _create_task(api, owner, pid, requirement_id, "first")
    second = _create_task(api, owner, pid, requirement_id, "second")
    _seed_runs(api, user["userId"], first, "stage-first")

    response = api.get(f"/v1/projects/{pid}/code-risk-analysis-tasks/latest-runs", headers=owner)

    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert [item["taskId"] for item in items] == [first]
    assert items[0]["status"] == "success"
    assert items[0]["runId"] == "exec-b"
    assert second not in {item["taskId"] for item in items}


def test_latest_runs_honor_project_read_access(api):  # noqa: F811
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    _, outsider = account(api, "outsider")
    pid = project(api, owner)
    requirement_id = requirement(api, owner, pid)
    _create_task(api, owner, pid, requirement_id, "first")

    api.post(
        f"/v1/projects/{pid}/members",
        headers=owner,
        json={"name": "viewer", "role": "viewer"},
    )
    allowed = api.get(f"/v1/projects/{pid}/code-risk-analysis-tasks/latest-runs", headers=viewer)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["items"] == []

    denied = api.get(f"/v1/projects/{pid}/code-risk-analysis-tasks/latest-runs", headers=outsider)
    assert denied.status_code == 403
