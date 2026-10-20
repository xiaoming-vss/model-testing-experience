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
