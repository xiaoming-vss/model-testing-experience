"""Shared preparation for bug api tests; no collected cases."""

from support.project_api import api as api


def create_bug(api, headers, pid, sprint_id, title="登录失败", reporter=None, **overrides):
    body = {
        "title": title,
        "assigneeUserId": overrides.pop("assigneeUserId", None)
        or (reporter["userId"] if reporter else None),
        "severity": "serious",
        "priority": "high",
        "foundSprintId": sprint_id,
        "descriptionHtml": "<p>现象与复现步骤</p>",
        **overrides,
    }
    if body["assigneeUserId"] is None:
        body.pop("assigneeUserId")
    response = api.post(f"/v1/projects/{pid}/bugs", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def get_bug(api, headers, bug_id):
    response = api.get(f"/v1/bugs/{bug_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def transition(api, headers, bug_id, action, **fields):
    if action == "submit_fix":
        fields.setdefault("resolvedBuild", "trunk")
    return api.post(
        f"/v1/bugs/{bug_id}/transition", headers=headers, json={"action": action, **fields}
    )


def activities_of(api, headers, bug_id):
    response = api.get(f"/v1/bugs/{bug_id}/activities", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]
