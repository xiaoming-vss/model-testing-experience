"""API 测试集归属变更在真实 HTTP 边界上的行为。"""

from support.project_api import account, api, project, requirement  # noqa: F401


def test_update_collection_requirement_updates_both_requirement_lists(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    original = requirement(api, owner, pid)
    sprint = api.get(f"/v1/requirements/{original}", headers=owner).json()["data"]["sprintId"]
    response = api.post(
        f"/v1/sprints/{sprint}/requirements", headers=owner, json={"name": "target"}
    )
    assert response.status_code == 200
    target = response.json()["data"]["requirementId"]
    created = api.post(
        f"/v1/requirements/{original}/api-collections", headers=owner, json={"name": "demo"}
    )
    collection_id = created.json()["data"]["collectionId"]
    case = api.post(
        f"/v1/api-collections/{collection_id}/cases",
        headers=owner,
        json={"name": "登录", "method": "GET", "urlTemplate": "/login"},
    )
    assert case.status_code == 200
    updated = api.patch(
        f"/v1/api-collections/{collection_id}", headers=owner, json={"requirementId": target}
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["requirementId"] == target
    assert (
        api.get(f"/v1/api-collections/{collection_id}/cases", headers=owner).json()["data"][
            "items"
        ][0]["caseId"]
        == case.json()["data"]["caseId"]
    )
    assert (
        api.get(f"/v1/requirements/{original}/api-collections", headers=owner).json()["data"][
            "total"
        ]
        == 0
    )
    assert (
        api.get(f"/v1/requirements/{target}/api-collections", headers=owner).json()["data"][
            "items"
        ][0]["collectionId"]
        == collection_id
    )


def test_reassignment_rejects_cross_project_and_missing_permission(api):  # noqa: F811
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    _, member = account(api, "member")
    first_project = project(api, owner)
    second_project = project(api, owner, "another")
    original = requirement(api, owner, first_project)
    other = requirement(api, owner, second_project)
    created = api.post(
        f"/v1/requirements/{original}/api-collections", headers=owner, json={"name": "demo"}
    )
    collection_id = created.json()["data"]["collectionId"]
    response = api.patch(
        f"/v1/api-collections/{collection_id}", headers=owner, json={"requirementId": other}
    )
    assert response.status_code == 400
    assert (
        api.get(f"/v1/api-collections/{collection_id}", headers=owner).json()["data"][
            "requirementId"
        ]
        == original
    )
    api.post(
        f"/v1/projects/{first_project}/members",
        headers=owner,
        json={"name": "viewer", "role": "viewer"},
    )
    response = api.patch(
        f"/v1/api-collections/{collection_id}", headers=viewer, json={"requirementId": other}
    )
    assert response.status_code == 403
    api.post(
        f"/v1/projects/{first_project}/members",
        headers=owner,
        json={"name": "member", "role": "member"},
    )
    response = api.patch(
        f"/v1/api-collections/{collection_id}", headers=member, json={"requirementId": other}
    )
    assert response.status_code == 403


def test_reassignment_duplicate_name_preserves_original_requirement(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    original = requirement(api, owner, pid)
    sprint = api.get(f"/v1/requirements/{original}", headers=owner).json()["data"]["sprintId"]
    target = api.post(
        f"/v1/sprints/{sprint}/requirements", headers=owner, json={"name": "target"}
    ).json()["data"]["requirementId"]
    collection_id = api.post(
        f"/v1/requirements/{original}/api-collections", headers=owner, json={"name": "demo"}
    ).json()["data"]["collectionId"]
    api.post(f"/v1/requirements/{target}/api-collections", headers=owner, json={"name": "demo"})
    response = api.patch(
        f"/v1/api-collections/{collection_id}", headers=owner, json={"requirementId": target}
    )
    assert response.status_code == 409
    assert (
        api.get(f"/v1/api-collections/{collection_id}", headers=owner).json()["data"][
            "requirementId"
        ]
        == original
    )
