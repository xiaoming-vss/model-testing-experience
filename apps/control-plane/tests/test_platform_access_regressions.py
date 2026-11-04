import pytest
from support.project_api import account, project, requirement
from support.project_api import api as api


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
