"""项目级 API 测试集列表：一次读取代替按需求扇出。"""

from support.project_api import account, api, project, requirement  # noqa: F401


def _create_collection(client, headers, requirement_id, name):
    response = client.post(
        f"/v1/requirements/{requirement_id}/api-collections",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["collectionId"]


def test_project_list_returns_collections_across_requirements(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    first_requirement = requirement(api, owner, pid)
    sprint_id = api.get(f"/v1/requirements/{first_requirement}", headers=owner).json()["data"][
        "sprintId"
    ]
    second_requirement = api.post(
        f"/v1/sprints/{sprint_id}/requirements", headers=owner, json={"name": "second"}
    ).json()["data"]["requirementId"]
    first = _create_collection(api, owner, first_requirement, "first")
    second = _create_collection(api, owner, second_requirement, "second")
    other_project = project(api, owner, "other")
    other_requirement = requirement(api, owner, other_project)
    _create_collection(api, owner, other_requirement, "elsewhere")

    response = api.get(f"/v1/projects/{pid}/api-collections", headers=owner)

    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert response.json()["data"]["total"] == 2
    assert {item["collectionId"] for item in items} == {first, second}
    by_id = {item["collectionId"]: item for item in items}
    assert by_id[first]["requirementId"] == first_requirement
    assert by_id[second]["requirementId"] == second_requirement


def test_project_list_honors_project_read_access(api):  # noqa: F811
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    _, outsider = account(api, "outsider")
    pid = project(api, owner)
    requirement_id = requirement(api, owner, pid)
    collection_id = _create_collection(api, owner, requirement_id, "demo")

    api.post(
        f"/v1/projects/{pid}/members",
        headers=owner,
        json={"name": "viewer", "role": "viewer"},
    )
    allowed = api.get(f"/v1/projects/{pid}/api-collections", headers=viewer)
    assert allowed.status_code == 200, allowed.text
    assert [item["collectionId"] for item in allowed.json()["data"]["items"]] == [collection_id]

    denied = api.get(f"/v1/projects/{pid}/api-collections", headers=outsider)
    assert denied.status_code == 403
