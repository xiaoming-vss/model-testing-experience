from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from support.remaining_control_plane import (
    FakeUpload,
)

from testing_agent.core.errors import (
    ErrApiCollectionImportInvalid,
)
from testing_agent.services import api_collection
from testing_agent.services.import_payload import read_import_payload


async def test_read_import_payload_accepts_uploaded_yaml_file():
    payload = await read_import_payload(
        None,
        FakeUpload(b"cases:\n  - name: imported\n    method: POST\n"),
    )

    assert payload == {"cases": [{"name": "imported", "method": "POST"}]}


@pytest.mark.asyncio
async def test_api_collection_import_accepts_go_generated_yaml_sample(monkeypatch):
    class FakeApiCollectionRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []

        async def get_collection(self, collection_id):
            assert collection_id == "collection-1"
            return SimpleNamespace(
                collection_id="collection-1",
                project_id="project-1",
                requirement_id="requirement-1",
            )

        async def get_requirement(self, requirement_id):
            return SimpleNamespace(sprint_id="sprint-1")

        async def get_sprint(self, sprint_id):
            return SimpleNamespace(project_id="project-1")

        async def get_project(self, project_id):
            return SimpleNamespace(user_id="user-1", project_id="project-1")

        async def exists_case_by_collection_and_name(self, collection_id, name):
            return False

        def add(self, row):
            self.rows.append(row)

        async def flush(self):
            return None

        async def commit(self):
            return None

    ids = iter([f"id-{index}" for index in range(1, 40)])
    monkeypatch.setattr(api_collection, "new_id", lambda: next(ids))
    monkeypatch.setattr("testing_agent.services.api_import_entities.new_id", lambda: next(ids))
    service = api_collection.ApiCollectionService(FakeApiCollectionRepository())
    payload = """
cases:
  - name: account_login
    orderNo: 1
    method: POST
    urlTemplate: /v1/login
    headers:
      Content-Type: application/json
    bodyType: json
    bodyJson:
      name: test_user
      password: test_password_123
    extractRules:
      - name: 提取accessToken
        orderNo: 1
        source: body_jsonpath
        sourceExpr: $.data.accessToken
        varKey: access_token
    assertRules:
      - name: 断言状态码为200
        orderNo: 1
        assertSource: status_code
        comparator: eq
        expectedValue: "200"
      - name: 断言返回accessToken存在
        orderNo: 2
        assertSource: body_jsonpath
        targetExpr: $.data.accessToken
        comparator: exists
  - name: get_project_list
    orderNo: 2
    method: GET
    urlTemplate: /v1/projects
    headers:
      Authorization: Bearer {{access_token}}
    bodyType: none
    extractRules:
      - name: 提取首个projectId
        orderNo: 1
        source: body_jsonpath
        sourceExpr: $.data[0].projectId
        varKey: project_id
    assertRules:
      - name: 断言状态码为200
        orderNo: 1
        assertSource: status_code
        comparator: eq
        expectedValue: "200"
"""

    result = await service.import_cases(
        "user-1",
        "collection-1",
        None,
        FakeUpload(payload.encode("utf-8"), "generated.yaml"),
    )

    assert result == {
        "collectionId": "collection-1",
        "importedCaseCount": 2,
        "importedExtractRuleCount": 2,
        "importedAssertRuleCount": 3,
    }


@pytest.mark.asyncio
async def test_api_collection_import_rejects_body_json_for_none_like_go():
    class FakeApiCollectionRepository:
        session = AuthorizationDatabase()

        async def get_collection(self, collection_id):
            return SimpleNamespace(
                collection_id="collection-1",
                project_id="project-1",
                requirement_id="requirement-1",
            )

        async def get_requirement(self, requirement_id):
            return SimpleNamespace(sprint_id="sprint-1")

        async def get_sprint(self, sprint_id):
            return SimpleNamespace(project_id="project-1")

        async def get_project(self, project_id):
            return SimpleNamespace(user_id="user-1", project_id="project-1")

        async def exists_case_by_collection_and_name(self, collection_id, name):
            return False

    service = api_collection.ApiCollectionService(FakeApiCollectionRepository())
    payload = (
        b"cases:\n  - name: bad\n    method: GET\n"
        b"    urlTemplate: /ping\n    bodyType: none\n    bodyJson: {}\n"
    )

    with pytest.raises(type(ErrApiCollectionImportInvalid)) as exc:
        await service.import_cases(
            "user-1",
            "collection-1",
            None,
            FakeUpload(payload, "bad.yaml"),
        )

    assert "bodyType=none" in str(exc.value)
