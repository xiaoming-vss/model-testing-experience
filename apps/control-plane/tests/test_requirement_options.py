"""需求下拉选项接口：跨迭代摘要、无正文、项目权限。"""

from support.project_api import account, api, project, requirement  # noqa: F401


def _second_requirement(client, headers, project_id, sprint_name, requirement_name):
    sprint = client.post(
        f"/v1/projects/{project_id}/sprints",
        headers=headers,
        json={
            "name": sprint_name,
            "startTime": "2026-10-01T00:00:00Z",
            "endTime": "2026-11-01T00:00:00Z",
        },
    )
    assert sprint.status_code == 200, sprint.text
    sprint_id = sprint.json()["data"]["sprintId"]
    created = client.post(
        f"/v1/sprints/{sprint_id}/requirements",
        headers=headers,
        json={"name": requirement_name},
    )
    assert created.status_code == 200, created.text
    return sprint_id, created.json()["data"]["requirementId"]


def test_options_cover_all_sprints_without_document_content(api):  # noqa: F811
    _, owner = account(api, "owner")
    project_id = project(api, owner)
    first_requirement = requirement(api, owner, project_id)
    first_sprint = api.get(f"/v1/requirements/{first_requirement}", headers=owner).json()["data"][
        "sprintId"
    ]
    second_sprint, second_requirement = _second_requirement(
        api, owner, project_id, "iteration-2", "second"
    )
    other_project = project(api, owner, "other")
    requirement(api, owner, other_project)

    response = api.get(f"/v1/projects/{project_id}/requirements/options", headers=owner)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 2
    by_id = {item["requirementId"]: item for item in data["items"]}
    assert set(by_id) == {first_requirement, second_requirement}
    assert by_id[first_requirement]["sprintId"] == first_sprint
    assert by_id[first_requirement]["sprintName"] == "iteration"
    assert by_id[second_requirement]["sprintId"] == second_sprint
    assert by_id[second_requirement]["sprintName"] == "iteration-2"
    assert by_id[second_requirement]["name"] == "second"
    assert all("documentContent" not in item for item in data["items"])
    assert all("documentType" not in item for item in data["items"])


def test_options_honor_project_read_access(api):  # noqa: F811
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    _, outsider = account(api, "outsider")
    project_id = project(api, owner)
    requirement(api, owner, project_id)

    api.post(
        f"/v1/projects/{project_id}/members",
        headers=owner,
        json={"name": "viewer", "role": "viewer"},
    )
    allowed = api.get(f"/v1/projects/{project_id}/requirements/options", headers=viewer)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["total"] == 1

    denied = api.get(f"/v1/projects/{project_id}/requirements/options", headers=outsider)
    assert denied.status_code == 403
    missing = api.get("/v1/projects/missing/requirements/options", headers=owner)
    assert missing.status_code == 404
