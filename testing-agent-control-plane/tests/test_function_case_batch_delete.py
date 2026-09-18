"""Batch deletion uses one authorized, suite-scoped transaction."""

import pytest
from test_project_membership_api import account, project, requirement
from test_project_membership_api import api as api


def setup_cases(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    sid = api.post(
        f"/v1/requirements/{rid}/function-test-suites", headers=owner, json={"name": "suite"}
    ).json()["data"]["suiteId"]
    url = f"/v1/function-test-suites/{sid}/cases"
    ids = [
        api.post(url, headers=owner, json={"title": f"case {i}"}).json()["data"]["caseId"]
        for i in range(3)
    ]
    return owner, pid, rid, sid, url, ids


def test_deletes_only_selected_and_deduplicates(api):
    owner, _, rid, sid, url, ids = setup_cases(api)
    response = api.post(
        url + "/batch-delete", headers=owner, json={"caseIds": [ids[0], ids[0], ids[2]]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"deletedIds": [ids[0], ids[2]], "deletedCount": 2}
    assert [c["caseId"] for c in api.get(url, headers=owner).json()["data"]["items"]] == [ids[1]]
    suites = api.get(f"/v1/requirements/{rid}/function-test-suites", headers=owner).json()["data"][
        "items"
    ]
    assert next(s for s in suites if s["suiteId"] == sid)["caseCount"] == 1


@pytest.mark.parametrize("invalid", ["empty", "missing", "foreign"])
def test_invalid_batch_keeps_all_cases(api, invalid):
    owner, _, rid, _, url, ids = setup_cases(api)
    selected = []
    if invalid == "missing":
        selected = [ids[0], "missing-id"]
    elif invalid == "foreign":
        sid = api.post(
            f"/v1/requirements/{rid}/function-test-suites", headers=owner, json={"name": "other"}
        ).json()["data"]["suiteId"]
        cid = api.post(
            f"/v1/function-test-suites/{sid}/cases", headers=owner, json={"title": "foreign"}
        ).json()["data"]["caseId"]
        selected = [ids[0], cid]
    response = api.post(url + "/batch-delete", headers=owner, json={"caseIds": selected})
    assert response.status_code in (400, 404, 422), response.text
    assert api.get(url, headers=owner).json()["data"]["total"] == 3


def test_readonly_cannot_delete(api):
    owner, pid, _, _, url, ids = setup_cases(api)
    _, viewer = account(api, "viewer")
    response = api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
    )
    assert response.status_code == 200, response.text
    response = api.post(url + "/batch-delete", headers=viewer, json={"caseIds": ids})
    assert response.status_code == 403, response.text
    assert api.get(url, headers=owner).json()["data"]["total"] == 3


def test_failure_after_first_delete_rolls_back(api, monkeypatch):
    from testing_agent.core.errors import ErrNotFound
    from testing_agent.repositories.function_test_case import FunctionTestCaseRepository

    owner, _, _, _, url, ids = setup_cases(api)
    original = FunctionTestCaseRepository.hard_delete
    count = 0

    async def fail_second(self, obj):
        nonlocal count
        count += 1
        if count == 2:
            raise ErrNotFound
        await original(self, obj)

    monkeypatch.setattr(FunctionTestCaseRepository, "hard_delete", fail_second)
    response = api.post(url + "/batch-delete", headers=owner, json={"caseIds": ids})
    assert response.status_code == 404
    assert api.get(url, headers=owner).json()["data"]["total"] == 3
