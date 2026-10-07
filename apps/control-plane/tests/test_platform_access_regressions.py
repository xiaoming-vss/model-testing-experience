import pytest
from test_project_membership_api import account, project, requirement
from test_project_membership_api import api as api


@pytest.mark.parametrize("kind", ["api-case-generate", "function-case-generate"])
def test_task_cannot_reveal_other_project_requirement(api, kind):
    _, owner = account(api, "scope-owner")
    _, member = account(api, "scope-member")
    target = project(api, owner, "shared-target")
    private = project(api, owner, "private-source")
    assert (
        api.post(
            f"/v1/projects/{target}/members",
            headers=owner,
            json={"name": "scope-member", "role": "member"},
        ).status_code
        == 200
    )
    rid = requirement(api, owner, private)
    assert (
        api.patch(
            f"/v1/requirements/{rid}",
            headers=owner,
            json={"documentContent": "PRIVATE_PROJECT_AUDIT_MARKER"},
        ).status_code
        == 200
    )
    assert api.get(f"/v1/requirements/{rid}", headers=member).status_code == 403
    created = api.post(
        f"/v1/projects/{target}/{kind}-tasks",
        headers=owner,
        json={"name": "scope-probe", "requirementId": rid},
    )
    assert created.status_code in (400, 403, 404), "Cross-project task reference accepted"


@pytest.mark.parametrize("kind", ["api-case-generate", "function-case-generate"])
def test_task_cannot_reference_other_project_sprint(api, kind):
    _, owner = account(api, "sprint-scope-owner")
    target = project(api, owner, "target")
    private = project(api, owner, "source")
    rid = requirement(api, owner, private)
    sid = api.get(f"/v1/requirements/{rid}", headers=owner).json()["data"]["sprintId"]
    response = api.post(
        f"/v1/projects/{target}/{kind}-tasks",
        headers=owner,
        json={"name": "sprint-scope", "sprintId": sid},
    )
    assert response.status_code in (400, 403, 404), (
        f"Cross-project sprint accepted: {response.status_code}"
    )


@pytest.mark.parametrize("kind", ["ui-case-generate", "requirement-analysis", "code-risk-analysis"])
def test_other_task_kinds_reject_cross_project_requirement(api, kind):
    _, owner = account(api, "control-owner")
    target = project(api, owner, "target")
    source = project(api, owner, "source")
    rid = requirement(api, owner, source)
    response = api.post(
        f"/v1/projects/{target}/{kind}-tasks",
        headers=owner,
        json={"name": "scope-control", "requirementId": rid},
    )
    assert response.status_code in (400, 403, 404)


def test_repeated_error_requests_do_not_retain_growing_request_tracebacks(api):
    from testing_agent.core.errors import ErrUnauthorized

    def depth():
        current = ErrUnauthorized.__traceback__
        count = 0
        while current:
            count += 1
            current = current.tb_next
        return count

    before = depth()
    for _ in range(20):
        response = api.get("/v1/projects")
        assert response.status_code == 401
    after = depth()
    assert after == before == 0, "Error definitions must not retain request traceback frames"


@pytest.mark.parametrize("confirm_overwrite", [False, True])
def test_viewer_cannot_import_function_candidates_into_formal_assets(api, confirm_overwrite):
    import asyncio

    from testing_agent.models.ai_generate_execution import (
        AiGenerateRunStage,
        AiGenerateStageAttempt,
    )
    from testing_agent.models.ai_generate_task import AiGenerateTaskRun

    owner_user, owner = account(api, "import-owner")
    _, viewer = account(api, "import-viewer")
    pid = project(api, owner, "import-project")
    rid = requirement(api, owner, pid)
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "import-viewer", "role": "viewer"},
        ).status_code
        == 200
    )
    created = api.post(
        f"/v1/projects/{pid}/function-case-generate-tasks",
        headers=owner,
        json={"name": "fixture-task", "requirementId": rid},
    )
    assert created.status_code == 200
    tid = created.json()["data"]["taskId"]

    async def seed():
        async with api.app.state.test_sessions() as session:
            session.add(
                AiGenerateTaskRun(
                    run_id="viewer-import-fixture",
                    task_id=tid,
                    trigger_user_id=owner_user["userId"],
                    status="success",
                    current_stage="completed",
                )
            )
            await session.flush()
            session.add(
                AiGenerateRunStage(
                    id="viewer-stage",
                    run_id="viewer-import-fixture",
                    stage="detailed_cases",
                    stage_order=2,
                    execution_status="success",
                    review_status="approved",
                    current_artifact_attempt_id="viewer-attempt",
                )
            )
            await session.flush()
            session.add(
                AiGenerateStageAttempt(
                    id="viewer-attempt",
                    stage_id="viewer-stage",
                    attempt_no=1,
                    operation="generate",
                    status="success",
                    output_content=(
                        "cases:\n  - module: Login\n    title: Fixture imported case\n"
                        "    steps: Click\n    expectedResults: Visible\n"
                    ),
                )
            )
            await session.commit()

    asyncio.run(seed())
    suites_url = f"/v1/requirements/{rid}/function-test-suites"
    assert api.post(suites_url, headers=viewer, json={"name": "forbidden"}).status_code == 403
    response = api.post(
        "/v1/function-case-generate-task-runs/viewer-import-fixture/import",
        headers=viewer,
        json={"confirmOverwrite": confirm_overwrite},
    )
    count = api.get(suites_url, headers=viewer).json()["data"]["total"]
    assert response.status_code == 403, (
        "Read-only member imported and modified formal function assets"
    )
    assert count == 0


def test_legacy_cross_project_task_is_blocked_on_read_update_and_run(api):
    import asyncio

    from sqlalchemy import select

    from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun

    user, owner = account(api, "legacy-owner")
    _, member = account(api, "legacy-member")
    target = project(api, owner, "shared")
    private = project(api, owner, "private")
    api.post(
        f"/v1/projects/{target}/members",
        headers=owner,
        json={"name": "legacy-member", "role": "member"},
    )
    local_req = requirement(api, owner, target)
    private_req = requirement(api, owner, private)
    sid = api.get(f"/v1/requirements/{private_req}", headers=owner).json()["data"]["sprintId"]
    created = api.post(
        f"/v1/projects/{target}/function-case-generate-tasks",
        headers=owner,
        json={"name": "legacy", "requirementId": local_req},
    )
    assert created.status_code == 200
    tid = created.json()["data"]["taskId"]

    async def seed():
        async with api.app.state.test_sessions() as session:
            task = await session.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == tid))
            task.requirement_id = private_req
            task.sprint_id = sid
            session.add(
                AiGenerateTaskRun(
                    run_id="legacy-run",
                    task_id=tid,
                    trigger_user_id=user["userId"],
                    status="success",
                    snapshot_json={"sourceContent": "PRIVATE_LEGACY_MARKER"},
                )
            )
            await session.commit()

    asyncio.run(seed())
    base = f"/v1/function-case-generate-tasks/{tid}"
    for response in (
        api.get(base, headers=member),
        api.get(f"{base}/runs", headers=member),
        api.get("/v1/function-case-generate-task-runs/legacy-run", headers=member),
        api.patch(base, headers=owner, json={"name": "edited"}),
        api.post(f"{base}/run", headers=owner, json={"connectionId": "unused"}),
    ):
        assert response.status_code in (400, 403, 404), response.text
        assert "PRIVATE_LEGACY_MARKER" not in response.text
