"""Server-side pagination, filters and status counts for AI task lists."""

import asyncio

from support.database_read_paths import NOW
from support.project_api import account, project, requirement
from support.project_api import api as api  # noqa: F401

from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage


def _seed_tasks(api, project_id: str, sprint_id: str, requirement_id: str) -> None:
    statuses = ["success"] * 5 + ["failed"] * 5 + ["running"] * 5 + ["waiting_review"] * 5

    async def seed():
        async with api.app.state.test_sessions() as session:
            session.add_all(
                [
                    AiGenerateTask(
                        task_id=f"task-{index}",
                        task_type="code_risk_analysis",
                        name=("登录" if index % 2 == 0 else "订单") + f"-task-{index}",
                        project_id=project_id,
                        sprint_id=sprint_id,
                        requirement_id=requirement_id,
                        creator_user_id="user",
                        source_type="text",
                        source_content="secret-body",
                        created_at=NOW,
                    )
                    for index in range(25)
                ]
            )
            await session.flush()
            for index, status in enumerate(statuses):
                execution_id = f"execution-{index}"
                stage_id = f"stage-{index}"
                session.add_all(
                    [
                        AiExecution(
                            execution_id=execution_id,
                            task_id=f"task-{index}",
                            requested_by="user",
                            created_at=NOW,
                        ),
                        AiGenerationStage(
                            id=stage_id,
                            task_id=f"task-{index}",
                            stage="generate",
                            review_status="not_required",
                        ),
                    ]
                )
                await session.flush()
                session.add(
                    AiGenerationAttempt(
                        id=f"attempt-{index}",
                        stage_id=stage_id,
                        execution_id=execution_id,
                        attempt_no=1,
                        operation="generate",
                        status=status,
                        input_snapshot_json={"triggerType": "manual"},
                        output_content="result",
                        created_at=NOW,
                    )
                )
            await session.commit()

    asyncio.run(seed())


def _resources(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    sprint_id = api.get(f"/v1/requirements/{rid}", headers=owner).json()["data"]["sprintId"]
    _seed_tasks(api, pid, sprint_id, rid)
    return owner, pid, rid, sprint_id


def test_ai_task_list_paginates_and_reports_status_counts(api):  # noqa: F811
    owner, pid, _, _ = _resources(api)
    response = api.get(
        f"/v1/projects/{pid}/code-risk-analysis-tasks?page=1&pageSize=20", headers=owner
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 25
    assert len(data["items"]) == 20
    assert [item["taskId"] for item in data["items"]] == [
        f"task-{index}" for index in range(24, 4, -1)
    ]
    assert data["statusCounts"] == {
        "success": 5,
        "failed": 5,
        "running": 5,
        "waiting_review": 5,
        "": 5,
    }
    assert "sourceContent" not in data["items"][0]
    assert data["items"][0]["latestRunStatus"] == ""

    second = api.get(
        f"/v1/projects/{pid}/code-risk-analysis-tasks?page=2&pageSize=20", headers=owner
    ).json()["data"]
    assert second["total"] == 25
    assert [item["taskId"] for item in second["items"]] == [
        f"task-{index}" for index in range(4, -1, -1)
    ]

    # The default is paginated as well; callers must not assume a full list.
    default_page = api.get(f"/v1/projects/{pid}/code-risk-analysis-tasks", headers=owner).json()[
        "data"
    ]
    assert default_page["total"] == 25
    assert len(default_page["items"]) == 20


def test_ai_task_list_filters_and_status_buckets(api):  # noqa: F811
    owner, pid, rid, sprint_id = _resources(api)
    common = f"/v1/projects/{pid}/code-risk-analysis-tasks"

    for status, expected in [
        ("success", 5),
        ("failed", 5),
        ("in_progress", 5),
        ("waiting_review", 5),
    ]:
        filtered = api.get(f"{common}?status={status}&pageSize=100", headers=owner)
        assert filtered.status_code == 200, filtered.text
        data = filtered.json()["data"]
        assert data["total"] == expected
        assert len(data["items"]) == expected
        assert all(
            item["latestRunStatus"]
            in (
                {"success"}
                if status == "success"
                else {"failed", "error"}
                if status == "failed"
                else {"pending", "queued", "claimed", "running"}
                if status == "in_progress"
                else {"waiting_review"}
            )
            for item in data["items"]
        )
        # Counts exclude the status filter and still cover every task.
        assert sum(data["statusCounts"].values()) == 25

    keyword = api.get(f"{common}?keyword=登录&pageSize=100", headers=owner).json()["data"]
    assert keyword["total"] == 13
    assert all("登录" in item["name"] for item in keyword["items"])

    assert api.get(f"{common}?sprintId={sprint_id}", headers=owner).json()["data"]["total"] == 25
    assert api.get(f"{common}?sprintId=missing", headers=owner).json()["data"]["total"] == 0
    assert api.get(f"{common}?requirementId={rid}", headers=owner).json()["data"]["total"] == 25
    assert api.get(f"{common}?requirementId=missing", headers=owner).json()["data"]["total"] == 0


def test_ai_task_list_bounds_access_and_detail_content(api):  # noqa: F811
    owner, pid, _, _ = _resources(api)
    common = f"/v1/projects/{pid}/code-risk-analysis-tasks"
    for params in ["page=0", "pageSize=0", "pageSize=101", "status=unknown"]:
        assert api.get(f"{common}?{params}", headers=owner).status_code == 400

    _, outsider = account(api, "outsider")
    assert api.get(common, headers=outsider).status_code == 403

    # status is deliberately unsupported outside code-risk analysis.
    assert (
        api.get(
            f"/v1/projects/{pid}/ui-case-generate-tasks?status=success", headers=owner
        ).status_code
        == 400
    )

    detail = api.get("/v1/code-risk-analysis-tasks/task-0", headers=owner)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["sourceContent"] == "secret-body"
