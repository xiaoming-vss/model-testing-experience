"""Sprint requirement list pagination and metadata-only payloads."""

import asyncio

from support.database_read_paths import NOW
from support.project_api import account, project
from support.project_api import api as api  # noqa: F401

from testing_agent.models.requirement import Requirement


def _seed_requirements(api, sprint_id: str) -> None:
    async def seed():
        async with api.app.state.test_sessions() as session:
            session.add_all(
                [
                    Requirement(
                        requirement_id=f"requirement-{index}",
                        sprint_id=sprint_id,
                        name=f"requirement-{index}",
                        document_type="richtext",
                        document_content="large-body",
                        document_filename=f"requirement-{index}.html",
                        created_at=NOW,
                    )
                    for index in range(25)
                ]
            )
            await session.commit()

    asyncio.run(seed())


def _sprint(api, owner, project_id: str) -> str:
    response = api.post(
        f"/v1/projects/{project_id}/sprints",
        headers=owner,
        json={
            "name": "iteration",
            "startTime": "2026-09-01T00:00:00Z",
            "endTime": "2026-10-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["sprintId"]


def test_sprint_requirements_paginate_without_document_content(api):  # noqa: F811
    _, owner = account(api, "owner")
    project_id = project(api, owner)
    sprint_id = _sprint(api, owner, project_id)
    _seed_requirements(api, sprint_id)

    first = api.get(f"/v1/sprints/{sprint_id}/requirements?page=1&pageSize=20", headers=owner)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["total"] == 25
    assert [item["requirementId"] for item in data["items"]] == [
        f"requirement-{index}" for index in range(24, 4, -1)
    ]
    assert all("documentContent" not in item for item in data["items"])
    assert data["items"][0]["documentFilename"] == "requirement-24.html"

    second = api.get(
        f"/v1/sprints/{sprint_id}/requirements?page=2&pageSize=20", headers=owner
    ).json()["data"]
    assert second["total"] == 25
    assert [item["requirementId"] for item in second["items"]] == [
        f"requirement-{index}" for index in range(4, -1, -1)
    ]

    beyond = api.get(
        f"/v1/sprints/{sprint_id}/requirements?page=3&pageSize=20", headers=owner
    ).json()["data"]
    assert beyond == {"total": 25, "items": []}

    default_page = api.get(f"/v1/sprints/{sprint_id}/requirements", headers=owner).json()["data"]
    assert default_page["total"] == 25
    assert len(default_page["items"]) == 20


def test_sprint_requirements_bounds_access_and_detail_content(api):  # noqa: F811
    _, owner = account(api, "owner")
    project_id = project(api, owner)
    sprint_id = _sprint(api, owner, project_id)
    _seed_requirements(api, sprint_id)

    for params in ["page=0", "pageSize=0", "pageSize=101"]:
        assert (
            api.get(f"/v1/sprints/{sprint_id}/requirements?{params}", headers=owner).status_code
            == 400
        )

    _, outsider = account(api, "outsider")
    assert api.get(f"/v1/sprints/{sprint_id}/requirements", headers=outsider).status_code == 403

    detail = api.get("/v1/requirements/requirement-0", headers=owner)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["documentContent"] == "large-body"
