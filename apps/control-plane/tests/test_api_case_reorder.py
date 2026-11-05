"""API 用例批量排序在 HTTP 边界上的行为。"""

from support.project_api import account, api, project, requirement  # noqa: F401


def _collection(client, headers):
    pid = project(client, headers)
    requirement_id = requirement(client, headers, pid)
    response = client.post(
        f"/v1/requirements/{requirement_id}/api-collections",
        headers=headers,
        json={"name": "demo"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["collectionId"]


def _cases(client, headers, collection_id):
    case_ids = []
    for name in ("first", "second", "third"):
        response = client.post(
            f"/v1/api-collections/{collection_id}/cases",
            headers=headers,
            json={"name": name, "method": "GET", "urlTemplate": f"/{name}"},
        )
        assert response.status_code == 200, response.text
        case_ids.append(response.json()["data"]["caseId"])
    return case_ids


def _listed_ids(client, headers, collection_id):
    response = client.get(f"/v1/api-collections/{collection_id}/cases", headers=headers)
    assert response.status_code == 200, response.text
    return [item["caseId"] for item in response.json()["data"]["items"]]


def test_reorder_persists_the_complete_order_in_one_request(api):  # noqa: F811
    _, owner = account(api, "owner")
    collection_id = _collection(api, owner)
    case_ids = _cases(api, owner, collection_id)

    response = api.patch(
        f"/v1/api-collections/{collection_id}/cases/reorder",
        headers=owner,
        json={"caseIds": list(reversed(case_ids))},
    )

    assert response.status_code == 200, response.text
    assert [item["caseId"] for item in response.json()["data"]["items"]] == list(reversed(case_ids))
    assert [item["orderNo"] for item in response.json()["data"]["items"]] == [1, 2, 3]
    assert _listed_ids(api, owner, collection_id) == list(reversed(case_ids))


def test_reorder_rejects_incomplete_or_unknown_case_sets(api):  # noqa: F811
    _, owner = account(api, "owner")
    collection_id = _collection(api, owner)
    case_ids = _cases(api, owner, collection_id)

    missing = api.patch(
        f"/v1/api-collections/{collection_id}/cases/reorder",
        headers=owner,
        json={"caseIds": case_ids[:2]},
    )
    assert missing.status_code == 400

    duplicated = api.patch(
        f"/v1/api-collections/{collection_id}/cases/reorder",
        headers=owner,
        json={"caseIds": [case_ids[0], case_ids[0], case_ids[1]]},
    )
    assert duplicated.status_code == 400

    unknown = api.patch(
        f"/v1/api-collections/{collection_id}/cases/reorder",
        headers=owner,
        json={"caseIds": [*case_ids, "missing-case"]},
    )
    assert unknown.status_code == 400

    undeclared = api.patch(
        f"/v1/api-collections/{collection_id}/cases/reorder",
        headers=owner,
        json={"caseIds": case_ids, "order": [1, 2, 3]},
    )
    assert undeclared.status_code == 400

    assert _listed_ids(api, owner, collection_id) == case_ids


def test_reorder_requires_write_permission(api):  # noqa: F811
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    collection_id = _collection(api, owner)
    case_ids = _cases(api, owner, collection_id)
    pid = api.get(f"/v1/api-collections/{collection_id}", headers=owner).json()["data"][
        "requirementId"
    ]
    sprint_id = api.get(f"/v1/requirements/{pid}", headers=owner).json()["data"]["sprintId"]
    project_id = api.get(f"/v1/sprints/{sprint_id}", headers=owner).json()["data"]["projectId"]
    api.post(
        f"/v1/projects/{project_id}/members",
        headers=owner,
        json={"name": "viewer", "role": "viewer"},
    )

    response = api.patch(
        f"/v1/api-collections/{collection_id}/cases/reorder",
        headers=viewer,
        json={"caseIds": list(reversed(case_ids))},
    )

    assert response.status_code == 403
    assert _listed_ids(api, owner, collection_id) == case_ids
