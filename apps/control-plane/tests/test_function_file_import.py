import json
from uuid import UUID

import pytest
from support.function_case_library import make_requirement, make_sprint, make_suite
from support.project_api import account, project
from support.project_api import api as api

from testing_agent.repositories.function_test_case import FunctionTestCaseRepository


@pytest.mark.parametrize("failure", ["invalid_second_item", "commit_failure"])
def test_file_import_is_atomic_and_can_be_retried(api, monkeypatch, failure):
    _, owner = account(api, "file-owner")
    pid = project(api, owner)
    suite = make_suite(api, owner, make_requirement(api, owner, make_sprint(api, owner, pid)))
    endpoint = f"/v1/function-test-suites/{suite}/cases/import"
    content = {
        "preconditions": ["已登录"],
        "steps": [{"action": "打开\n提交", "expected": "保存成功"}],
    }
    valid = {"title": "文件用例", "content": content}
    payload = {"cases": [valid]}
    original_commit = FunctionTestCaseRepository.commit

    async def unavailable(repository):
        await repository.session.flush()
        raise RuntimeError("injected commit failure")

    if failure == "invalid_second_item":
        payload["cases"].append({"title": "无效", "content": {"steps": "wrong"}})
    else:
        monkeypatch.setattr(FunctionTestCaseRepository, "commit", unavailable)
    response = api.post(
        endpoint,
        headers=owner,
        files={"file": ("cases.json", json.dumps(payload), "application/json")},
    )
    assert response.status_code == (500 if failure == "commit_failure" else 400)
    listing = api.get(f"/v1/function-test-suites/{suite}/cases", headers=owner)
    assert listing.json()["data"]["items"] == []

    monkeypatch.setattr(FunctionTestCaseRepository, "commit", original_commit)
    retried = api.post(
        endpoint,
        headers=owner,
        files={"file": ("cases.json", json.dumps({"cases": [valid]}), "application/json")},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["data"] == {"imported": 1}
    stored = api.get(f"/v1/function-test-suites/{suite}/cases", headers=owner).json()["data"][
        "items"
    ]
    assert len(stored) == 1
    assert UUID(stored[0]["caseId"]).version == 4
    assert stored[0]["content"] == content


def test_local_case_creation_does_not_construct_remote_export_client(api, monkeypatch):
    _, owner = account(api, "local-owner")
    pid = project(api, owner)
    suite = make_suite(api, owner, make_requirement(api, owner, make_sprint(api, owner, pid)))

    def forbidden_client():
        raise AssertionError("Local assets must not construct a remote export client")

    monkeypatch.setattr("testing_agent.api.deps.ZentaoMcpCases", forbidden_client)
    response = api.post(
        f"/v1/function-test-suites/{suite}/cases", headers=owner, json={"title": "本地用例"}
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("bad_item", ["not-an-object", {"title": "bad", "orderNo": "NaN"}])
def test_invalid_file_item_is_reported_without_partial_assets(api, bad_item):
    _, owner = account(api, "invalid-file-owner")
    pid = project(api, owner)
    suite = make_suite(api, owner, make_requirement(api, owner, make_sprint(api, owner, pid)))
    response = api.post(
        f"/v1/function-test-suites/{suite}/cases/import",
        headers=owner,
        files={"file": ("cases.json", json.dumps({"cases": [{"title": "valid"}, bad_item]}))},
    )
    assert response.status_code == 400
    assert "第 2 条" in response.json()["message"]
    assert (
        api.get(f"/v1/function-test-suites/{suite}/cases", headers=owner).json()["data"]["items"]
        == []
    )


def test_import_releases_read_transaction_and_rechecks_target_after_parsing(api, monkeypatch):
    from sqlalchemy import delete

    from testing_agent.models.function_test_suite import FunctionTestSuite
    from testing_agent.services import function_case_import
    from testing_agent.services.function_case_access import FunctionCaseAccess

    _, owner = account(api, "recheck-file-owner")
    pid = project(api, owner)
    suite = make_suite(api, owner, make_requirement(api, owner, make_sprint(api, owner, pid)))
    sessions = []
    original_access = FunctionCaseAccess.get_accessible_suite
    original_parse = function_case_import.read_import_payload

    async def access(service, *args, **kwargs):
        sessions.append(service.repository.session)
        return await original_access(service, *args, **kwargs)

    async def parse(payload, file):
        assert not sessions[-1].in_transaction()
        async with api.app.state.test_sessions() as session:
            await session.execute(
                delete(FunctionTestSuite).where(FunctionTestSuite.suite_id == suite)
            )
            await session.commit()
        return await original_parse(payload, file)

    monkeypatch.setattr(FunctionCaseAccess, "get_accessible_suite", access)
    monkeypatch.setattr(function_case_import, "read_import_payload", parse)
    response = api.post(
        f"/v1/function-test-suites/{suite}/cases/import",
        headers=owner,
        files={"file": ("cases.json", json.dumps({"cases": [{"title": "valid"}]}))},
    )
    assert response.status_code == 404
    assert len(sessions) == 2
