"""HTTP scope, authentication and empty-chain contracts for the panorama."""

import asyncio
from datetime import UTC, datetime, timedelta

from support.openapi_schema import openapi_schema
from support.project_api import account, api, project  # noqa: F401

from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint


def seed_requirement(client, project_id):
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
                ]
            )
            await session.commit()

    asyncio.run(insert())


def test_generation_version_import_routes_are_public():
    paths = openapi_schema()["paths"]
    assert (
        "get"
        in paths[
            "/v1/requirements/{requirementId}/generation/{kind}/versions/{versionId}/import-options"
        ]
    )
    assert (
        "post"
        in paths["/v1/requirements/{requirementId}/generation/{kind}/versions/{versionId}/import"]
    )
    assert "put" in paths["/v1/requirements/{requirementId}/generation/{kind}/stages/{stage}/draft"]


def test_generation_panorama_scope_and_empty_chain_contract(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    seed_requirement(api, pid)
    _, viewer = account(api, "viewer")
    _, developer = account(api, "developer")
    _, stranger = account(api, "stranger")
    for name, role in [("viewer", "viewer"), ("developer", "developer")]:
        assert (
            api.post(
                f"/v1/projects/{pid}/members",
                headers=owner,
                json={"name": name, "role": role},
            ).status_code
            == 200
        )
    for headers, expected in [
        (owner, 200),
        (viewer, 200),
        (developer, 403),
        (stranger, 403),
    ]:
        assert api.get("/v1/requirements/req/generation", headers=headers).status_code == expected
        assert (
            api.get("/v1/requirements/req/generation/function", headers=headers).status_code
            == expected
        )
    for headers in (viewer, developer, stranger):
        response = api.put(
            "/v1/requirements/req/generation/function/stages/case_names/draft",
            headers=headers,
            json={"expectedAttemptId": "draft", "content": "{}"},
        )
        assert response.status_code == 403
    data = api.get("/v1/requirements/req/generation", headers=owner).json()["data"]
    assert [chain["kind"] for chain in data["chains"]] == [
        "requirement_analysis",
        "function",
        "api",
        "ui",
    ]
    function = next(chain for chain in data["chains"] if chain["kind"] == "function")
    assert function["configured"] is False
    assert [stage["stage"] for stage in function["stages"]] == [
        "requirement_analysis",
        "case_names",
        "detailed_cases",
    ]
    assert (
        api.post(
            "/v1/requirements/req/generation/function/stages/case_names/review",
            headers=owner,
            json={"action": "approve"},
        ).status_code
        == 400
    )
    assert api.get("/v1/requirements/other/generation/function", headers=owner).status_code == 200
    assert api.get("/v1/requirements/missing/generation/function", headers=owner).status_code == 404
    assert (
        api.post(
            "/v1/requirements/req/generation/function/stages/invented/review",
            headers=owner,
            json={"action": "approve"},
        ).status_code
        == 400
    )
