"""Shared preparation for function case library tests; no collected cases."""

from urllib.parse import urlencode

from support.project_api import api as api

SPRINT_BODY = {
    "name": "iteration",
    "startTime": "2026-09-01T00:00:00Z",
    "endTime": "2026-10-01T00:00:00Z",
}


def make_sprint(api, headers, pid, name="iteration"):
    response = api.post(
        f"/v1/projects/{pid}/sprints", headers=headers, json={**SPRINT_BODY, "name": name}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["sprintId"]


def make_requirement(api, headers, sprint_id, name="req"):
    response = api.post(
        f"/v1/sprints/{sprint_id}/requirements", headers=headers, json={"name": name}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["requirementId"]


def make_suite(api, headers, requirement_id, name="suite"):
    response = api.post(
        f"/v1/requirements/{requirement_id}/function-test-suites",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["suiteId"]


def make_case(api, headers, suite_id, **overrides):
    body = {"title": "case", **overrides}
    response = api.post(f"/v1/function-test-suites/{suite_id}/cases", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]["caseId"]


def list_library(api, headers, pid, **params):
    query = urlencode({key: value for key, value in params.items() if value not in ("", None)})
    suffix = f"?{query}" if query else ""
    response = api.get(f"/v1/projects/{pid}/function-test-cases{suffix}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]
