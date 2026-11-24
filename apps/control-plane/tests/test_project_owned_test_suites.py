"""项目级 API/UI 测试集：可选需求、生成链路约束和需求删除行为。"""

import asyncio

from sqlalchemy import select
from support.project_api import account, api, project, requirement  # noqa: F401

from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.ui_test_suite import UiTestSuite


def _set_effective_import(app, model, identity_column, identity, import_id):
    async def update():
        async with app.app.state.test_sessions() as session:
            row = await session.scalar(select(model).where(identity_column == identity))
            assert row is not None
            row.effective_import_id = import_id
            await session.commit()

    asyncio.run(update())


def test_project_level_suites_do_not_require_requirement(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)

    created_api = api.post(
        f"/v1/projects/{pid}/api-collections", headers=owner, json={"name": "api-regression"}
    )
    assert created_api.status_code == 200, created_api.text
    api_data = created_api.json()["data"]
    assert api_data["projectId"] == pid
    assert api_data["requirementId"] is None

    created_ui = api.post(
        f"/v1/projects/{pid}/ui-test-suites", headers=owner, json={"name": "ui-regression"}
    )
    assert created_ui.status_code == 200, created_ui.text
    ui_data = created_ui.json()["data"]
    assert ui_data["projectId"] == pid
    assert ui_data["requirementId"] is None

    project_apis = api.get(f"/v1/projects/{pid}/api-collections", headers=owner).json()["data"]
    assert {item["collectionId"] for item in project_apis["items"]} == {api_data["collectionId"]}
    project_uis = api.get(f"/v1/projects/{pid}/ui-test-suites", headers=owner).json()["data"]
    assert {item["suiteId"] for item in project_uis["items"]} == {ui_data["suiteId"]}
    assert (
        api.get(f"/v1/requirements/{rid}/api-collections", headers=owner).json()["data"]["total"]
        == 0
    )
    assert (
        api.get(f"/v1/requirements/{rid}/ui-test-suites", headers=owner).json()["data"]["total"]
        == 0
    )


def test_project_level_api_suite_runs_without_requirement(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    collection_id = api.post(
        f"/v1/projects/{pid}/api-collections", headers=owner, json={"name": "regression"}
    ).json()["data"]["collectionId"]
    environment_id = api.post(
        f"/v1/projects/{pid}/api-environments",
        headers=owner,
        json={"name": "api-env", "kind": "api", "baseUrl": "https://example.test"},
    ).json()["data"]["environmentId"]
    created = api.post(
        f"/v1/api-collections/{collection_id}/cases",
        headers=owner,
        json={"name": "ping", "method": "GET", "urlTemplate": "/ping"},
    )
    assert created.status_code == 200, created.text

    response = api.post(
        f"/v1/api-collections/{collection_id}/run",
        headers=owner,
        json={"environmentId": environment_id},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["projectId"] == pid
    assert data["requirementId"] is None
    assert data["sprintId"] is None
    assert data["triggerType"] == "manual"


def test_generated_suite_cannot_unlink_or_switch_requirement(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    original = requirement(api, owner, pid)
    sprint = api.get(f"/v1/requirements/{original}", headers=owner).json()["data"]["sprintId"]
    other = api.post(
        f"/v1/sprints/{sprint}/requirements", headers=owner, json={"name": "other"}
    ).json()["data"]["requirementId"]
    collection_id = api.post(
        f"/v1/requirements/{original}/api-collections", headers=owner, json={"name": "generated"}
    ).json()["data"]["collectionId"]
    _set_effective_import(
        api, ApiCollection, ApiCollection.collection_id, collection_id, "gi-generated"
    )

    unlink = api.patch(
        f"/v1/api-collections/{collection_id}", headers=owner, json={"requirementId": None}
    )
    assert unlink.status_code == 400, unlink.text
    switch = api.patch(
        f"/v1/api-collections/{collection_id}", headers=owner, json={"requirementId": other}
    )
    assert switch.status_code == 400, switch.text
    renamed = api.patch(f"/v1/api-collections/{collection_id}", headers=owner, json={"name": "new"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["requirementId"] == original


def test_manual_suite_can_link_change_and_unlink_requirement(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    first = requirement(api, owner, pid)
    sprint = api.get(f"/v1/requirements/{first}", headers=owner).json()["data"]["sprintId"]
    second = api.post(
        f"/v1/sprints/{sprint}/requirements", headers=owner, json={"name": "second"}
    ).json()["data"]["requirementId"]

    created = api.post(
        f"/v1/projects/{pid}/api-collections",
        headers=owner,
        json={"name": "manual", "requirementId": first},
    )
    assert created.status_code == 200, created.text
    collection_id = created.json()["data"]["collectionId"]
    assert created.json()["data"]["requirementId"] == first

    moved = api.patch(
        f"/v1/api-collections/{collection_id}", headers=owner, json={"requirementId": second}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["data"]["requirementId"] == second

    unlinked = api.patch(
        f"/v1/api-collections/{collection_id}", headers=owner, json={"requirementId": None}
    )
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["data"]["requirementId"] is None


def test_requirement_delete_detaches_suites_and_project_delete_blocks(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    sprint_id = api.get(f"/v1/requirements/{rid}", headers=owner).json()["data"]["sprintId"]
    collection_id = api.post(
        f"/v1/requirements/{rid}/api-collections", headers=owner, json={"name": "api"}
    ).json()["data"]["collectionId"]
    suite_id = api.post(
        f"/v1/requirements/{rid}/ui-test-suites", headers=owner, json={"name": "ui"}
    ).json()["data"]["suiteId"]

    deleted = api.delete(f"/v1/requirements/{rid}", headers=owner)
    assert deleted.status_code == 200, deleted.text
    detached_api = api.get(f"/v1/api-collections/{collection_id}", headers=owner).json()["data"]
    detached_ui = api.get(f"/v1/ui-test-suites/{suite_id}", headers=owner).json()["data"]
    assert detached_api["requirementId"] is None
    assert detached_ui["requirementId"] is None

    blocked = api.delete(f"/v1/projects/{pid}", headers=owner)
    assert blocked.status_code == 409, blocked.text
    assert "API 测试集" in blocked.json()["message"]

    assert api.delete(f"/v1/api-collections/{collection_id}", headers=owner).status_code == 200
    assert api.delete(f"/v1/ui-test-suites/{suite_id}", headers=owner).status_code == 200
    assert api.delete(f"/v1/sprints/{sprint_id}", headers=owner).status_code == 200
    assert api.delete(f"/v1/projects/{pid}", headers=owner).status_code == 200


def test_ui_generated_suite_cannot_unlink_requirement(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    suite_id = api.post(
        f"/v1/requirements/{rid}/ui-test-suites", headers=owner, json={"name": "generated-ui"}
    ).json()["data"]["suiteId"]
    _set_effective_import(api, UiTestSuite, UiTestSuite.suite_id, suite_id, "gi-generated-ui")

    response = api.patch(
        f"/v1/ui-test-suites/{suite_id}", headers=owner, json={"requirementId": None}
    )

    assert response.status_code == 400, response.text


def test_project_level_suite_names_are_unique_per_project(api):  # noqa: F811
    _, owner = account(api, "owner")
    pid = project(api, owner)

    for path in (
        f"/v1/projects/{pid}/api-collections",
        f"/v1/projects/{pid}/ui-test-suites",
    ):
        assert api.post(path, headers=owner, json={"name": "shared-name"}).status_code == 200
        duplicate = api.post(path, headers=owner, json={"name": "shared-name"})
        assert duplicate.status_code == 409, duplicate.text
