"""Real HTTP authorization/scope and response-loss retries, without worker/model calls."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from test_project_membership_api import account, api, project  # noqa: F401

from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint


def seed_requirement(client, project_id, user_id):
    async def insert():
        async with client.app.state.test_sessions() as session:
            now = datetime.now(UTC)
            session.add(
                Sprint(
                    sprint_id="s",
                    project_id=project_id,
                    name="s",
                    start_time=now,
                    end_time=now + timedelta(days=1),
                )
            )
            await session.flush()
            session.add_all(
                [
                    Requirement(requirement_id="req", sprint_id="s", name="登录需求"),
                    Requirement(requirement_id="other", sprint_id="s", name="其他需求"),
                    IntegrationConnection(
                        connection_id="mine",
                        user_id=user_id,
                        provider="llm",
                        project_id=project_id,
                        name="mine",
                        status="active",
                        secret_json={"apiKey": "isolated-test"},
                    ),
                ]
            )
            await session.commit()

    asyncio.run(insert())


def test_requirement_workspace_scope_roles_and_idempotent_run(api):  # noqa: F811
    user, owner = account(api, "owner")
    pid = project(api, owner)
    seed_requirement(api, pid, user["userId"])
    _, viewer = account(api, "viewer")
    _, developer = account(api, "developer")
    _, stranger = account(api, "stranger")
    _, member = account(api, "member")
    for name, role in [("viewer", "viewer"), ("developer", "developer"), ("member", "member")]:
        assert (
            api.post(
                f"/v1/projects/{pid}/members", headers=owner, json={"name": name, "role": role}
            ).status_code
            == 200
        )
    base = "/v1/requirements/req/design"
    for headers, expected in [(owner, 200), (viewer, 200), (developer, 403), (stranger, 403)]:
        assert api.get(base, headers=headers).status_code == expected
        assert api.get(base + "/api/runs", headers=headers).status_code == expected
    configuration = {"sourceContent": '{"openapi":"3.0.0","paths":{}}', "requestId": str(uuid4())}
    assert (
        api.post(base + "/api/configuration", headers=viewer, json=configuration).status_code == 403
    )
    first = api.post(base + "/api/configuration", headers=owner, json=configuration)
    assert first.status_code == 200, first.text
    task_id = first.json()["data"]["taskId"]
    second = api.post(base + "/api/configuration", headers=owner, json=configuration)
    assert second.status_code == 200, second.text
    assert second.json()["data"]["taskId"] == task_id
    run = {"taskId": task_id, "requestId": str(uuid4()), "connectionId": "mine"}
    assert api.post(base + "/api/run", headers=viewer, json=run).status_code == 403
    assert (
        api.post("/v1/requirements/other/design/api/run", headers=owner, json=run).status_code
        == 404
    )
    assert api.post(base + "/api/run", headers=member, json=run).status_code == 404
    first_run = api.post(base + "/api/run", headers=owner, json=run)
    assert first_run.status_code == 200, first_run.text
    second_run = api.post(base + "/api/run", headers=owner, json=run)
    assert second_run.status_code == 200, second_run.text
    assert first_run.json()["data"]["runId"] == second_run.json()["data"]["runId"]
    history = api.get(base + "/api/runs", headers=owner).json()["data"]
    assert history["total"] == 1
    assert "snapshotJson" not in history["items"][0]
    overview = api.get(base, headers=owner).json()["data"]
    assert overview["runCounts"] == {"api": 1, "ui": 0, "function": 0, "requirement_analysis": 0}
    assert overview["activeTaskIds"] == [task_id]
    assert not overview["adoptedUnderstanding"]
    assert api.get(base + "/api/runs?page=0", headers=owner).status_code == 400
    assert api.get(base + "/api/runs?pageSize=101", headers=owner).status_code == 400
    assert api.get(base + "/invented/runs", headers=owner).status_code == 400
    assert (
        api.post(base + "/api/configuration", headers=owner, json={"projectId": pid}).status_code
        == 400
    )
