"""Pagination contracts for API collection and UI suite run histories."""

import asyncio

from support.database_read_paths import NOW
from support.project_api import account, project, requirement
from support.project_api import api as api  # noqa: F401

from testing_agent.models.api_collection_run import ApiCollectionRun
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun


def _seed_runs(api, collection_id: str, suite_id: str) -> None:
    async def seed():
        async with api.app.state.test_sessions() as session:
            session.add_all(
                [
                    ApiCollectionRun(
                        collection_run_id=f"collection-run-{index}",
                        collection_id=collection_id,
                        environment_id="environment",
                        trigger_user_id="user",
                        status="success",
                        created_at=NOW,
                    )
                    for index in range(25)
                ]
            )
            session.add_all(
                [
                    UiTestSuiteRun(
                        suite_run_id=f"suite-run-{index}",
                        suite_id=suite_id,
                        trigger_user_id="user",
                        status="success",
                        created_at=NOW,
                    )
                    for index in range(25)
                ]
            )
            await session.commit()

    asyncio.run(seed())


def _resources(api, owner):
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    suite_id = api.post(
        f"/v1/requirements/{rid}/ui-test-suites", headers=owner, json={"name": "suite"}
    ).json()["data"]["suiteId"]
    collection_id = api.post(
        f"/v1/requirements/{rid}/api-collections", headers=owner, json={"name": "collection"}
    ).json()["data"]["collectionId"]
    return pid, suite_id, collection_id


def test_api_collection_run_history_paginates(api):  # noqa: F811
    _, owner = account(api, "owner")
    _, suite_id, collection_id = _resources(api, owner)
    _seed_runs(api, collection_id, suite_id)

    first = api.get(f"/v1/api-collections/{collection_id}/runs?page=1&pageSize=20", headers=owner)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["total"] == 25
    assert [item["collectionRunId"] for item in data["items"]] == [
        f"collection-run-{index}" for index in range(24, 4, -1)
    ]

    second = api.get(
        f"/v1/api-collections/{collection_id}/runs?page=2&pageSize=20", headers=owner
    ).json()["data"]
    assert second["total"] == 25
    assert [item["collectionRunId"] for item in second["items"]] == [
        f"collection-run-{index}" for index in range(4, -1, -1)
    ]

    beyond = api.get(
        f"/v1/api-collections/{collection_id}/runs?page=3&pageSize=20", headers=owner
    ).json()["data"]
    assert beyond == {"total": 25, "items": []}

    for params in ["page=0", "pageSize=0", "pageSize=101"]:
        assert (
            api.get(f"/v1/api-collections/{collection_id}/runs?{params}", headers=owner).status_code
            == 400
        )

    _, outsider = account(api, "outsider")
    assert api.get(f"/v1/api-collections/{collection_id}/runs", headers=outsider).status_code == 403


def test_ui_suite_run_history_paginates(api):  # noqa: F811
    _, owner = account(api, "owner")
    _, suite_id, collection_id = _resources(api, owner)
    _seed_runs(api, collection_id, suite_id)

    first = api.get(f"/v1/ui-test-suites/{suite_id}/runs?page=1&pageSize=20", headers=owner)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["total"] == 25
    assert [item["suiteRunId"] for item in data["items"]] == [
        f"suite-run-{index}" for index in range(24, 4, -1)
    ]

    second = api.get(
        f"/v1/ui-test-suites/{suite_id}/runs?page=2&pageSize=20", headers=owner
    ).json()["data"]
    assert second["total"] == 25
    assert [item["suiteRunId"] for item in second["items"]] == [
        f"suite-run-{index}" for index in range(4, -1, -1)
    ]

    beyond = api.get(
        f"/v1/ui-test-suites/{suite_id}/runs?page=3&pageSize=20", headers=owner
    ).json()["data"]
    assert beyond == {"total": 25, "items": []}

    for params in ["page=0", "pageSize=0", "pageSize=101"]:
        assert (
            api.get(f"/v1/ui-test-suites/{suite_id}/runs?{params}", headers=owner).status_code
            == 400
        )

    _, outsider = account(api, "outsider")
    assert api.get(f"/v1/ui-test-suites/{suite_id}/runs", headers=outsider).status_code == 403
