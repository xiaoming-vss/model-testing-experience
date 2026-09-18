from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase, AuthorizedRepositoryFixture
from fastapi.testclient import TestClient

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.app import create_app
from testing_agent.core.errors import (
    ErrApiCollectionImportInvalid,
    ErrBadRequest,
    ErrRemoteResourceAlreadyBound,
    ErrResourceBindingAlreadyExists,
    ErrZentaoRemoteResourceUnavailable,
)
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskReviewRequest,
    RequirementAnalysisRunRequest,
)
from testing_agent.schemas.api_run import RunApiCaseRequest
from testing_agent.schemas.workers import WorkerTaskEventRequest
from testing_agent.services import ai_generate_task as ai_tasks
from testing_agent.services import api_collection, worker
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.api_request_render import (
    api_case_request_template,
    render_api_case_request,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.resource_binding import ResourceBindingService
from testing_agent.services.zentao_auth import ZentaoAuthProvider


class FakeUpload:
    def __init__(self, content: bytes, filename: str = "cases.yaml"):
        self.content = content
        self.filename = filename

    async def read(self) -> bytes:
        return self.content


class FakeResourceBindingRepository:
    session = AuthorizationDatabase()

    def __init__(self):
        self.project = SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
        )
        self.rows = []
        self.active_local = None
        self.remote_exists = False
        self.committed = False
        self.refreshed = None

    async def get_project(self, project_id):
        assert project_id == "project-1"
        return self.project

    async def get_active_by_local_resource(self, resource_type, resource_id):
        assert (resource_type, resource_id) == ("project", "project-1")
        return self.active_local

    async def exists_active_by_remote_resource(
        self,
        provider,
        connection_id,
        remote_resource_type,
        remote_resource_id,
    ):
        assert provider == "zentao"
        assert connection_id == "conn-1"
        assert remote_resource_type == "project"
        assert remote_resource_id == "101"
        return self.remote_exists

    def add(self, binding):
        self.rows.append(binding)

    async def commit(self):
        self.committed = True

    async def refresh(self, row):
        self.refreshed = row


class FakeIntegrationConnectionService:
    async def resolve_zentao_access(self, user_id, connection_id, project_id=""):
        return await self.get_active_personal(user_id, "zentao", connection_id, project_id)

    async def get_active_personal(self, user_id, provider, connection_id, project_id=""):
        assert user_id == "user-1"
        assert provider == "zentao"
        assert connection_id == "conn-1"
        return SimpleNamespace(
            connection_id="conn-1",
            provider="zentao",
            status="active",
            base_url="https://zentao.example",
            access_token="token",
        )


class FakeZentaoResourceClient:
    session = AuthorizationDatabase()

    def __init__(self, *, deleted=False):
        self.deleted = deleted
        self.project_calls = []

    async def get_project(self, connection, remote_resource_id):
        self.project_calls.append((connection.connection_id, remote_resource_id))
        return SimpleNamespace(
            id=101,
            name="旧禅道项目",
            deleted=self.deleted,
        )


class FakeIntegrationRepositoryForZentaoBrowse:
    async def get(self, user_id, provider, connection_id, project_id=""):
        assert user_id == "user-1"
        assert provider == "zentao"
        assert connection_id == "conn-1"
        return SimpleNamespace(
            connection_id="conn-1",
            provider="zentao",
            status="active",
            base_url="https://zentao.example",
            access_token="token",
        )


class FakeZentaoBrowseClient:
    def __init__(self):
        self.calls = []

    async def list_projects(self, connection, page=1, page_size=100):
        self.calls.append(("projects", connection.connection_id, page, page_size))
        return {
            "items": [
                SimpleNamespace(
                    id=101,
                    name="项目A",
                    code="PA",
                    description="desc",
                    status="doing",
                    begin="2026-01-01",
                    end="2026-02-01",
                    created_at="2026-01-01T00:00:00Z",
                    updated_at="2026-01-02T00:00:00Z",
                    deleted=False,
                ),
                SimpleNamespace(id=102, name="已删除项目", deleted=True),
            ],
            "total": 2,
        }

    async def list_project_executions(self, connection, remote_project_id, page=1, page_size=100):
        self.calls.append(
            ("executions", connection.connection_id, remote_project_id, page, page_size)
        )
        return {
            "items": [
                SimpleNamespace(
                    id=201,
                    project_id=101,
                    name="执行A",
                    description="exec desc",
                    status="doing",
                    begin="2026-01-03",
                    end="2026-01-20",
                    parent_id=0,
                    created_at="",
                    updated_at="",
                    deleted=False,
                )
            ],
            "total": 1,
        }

    async def list_execution_testtasks(
        self,
        connection,
        remote_execution_id,
        page=1,
        page_size=100,
    ):
        self.calls.append(
            ("testtasks", connection.connection_id, remote_execution_id, page, page_size)
        )
        return {
            "items": [
                SimpleNamespace(
                    id=301,
                    project_id=101,
                    execution_id=201,
                    name="测试单A",
                    title="测试单标题",
                    description="",
                    status="doing",
                    type="feature",
                    owner="tester",
                    opened_by="pm",
                    begin="",
                    end="",
                    created_at="",
                    updated_at="",
                    deleted=False,
                )
            ],
            "total": 1,
        }

    async def list_execution_stories(self, connection, remote_execution_id):
        self.calls.append(("stories", connection.connection_id, remote_execution_id))
        return {
            "items": [
                SimpleNamespace(
                    id=401,
                    title="需求A",
                    product_id=1,
                    module_id=2,
                    plan_id=3,
                    status="active",
                    stage="developing",
                    priority="2",
                    assigned_to="dev",
                    opened_by="pm",
                    created_at="",
                    updated_at="",
                    deleted=False,
                )
            ],
            "total": 1,
        }

    async def list_execution_cases(self, connection, remote_execution_id, page=1, page_size=100):
        self.calls.append(("cases", connection.connection_id, remote_execution_id, page, page_size))
        return {
            "items": [
                SimpleNamespace(
                    id="501",
                    module="模块A",
                    title="用例A",
                    preconditions="前置",
                    steps="步骤",
                    expected_results="预期",
                    priority="1",
                    case_type="feature",
                    order_no=7,
                    deleted=False,
                )
            ],
            "total": 1,
        }


class FakeIntegrationRepositoryForConnectionAuth:
    session = AuthorizationDatabase()

    def __init__(self):
        self.rows = []
        self.commits = 0

    async def get(self, user_id, provider, connection_id, project_id=""):
        return next(
            (
                row
                for row in self.rows
                if row.user_id == user_id
                and row.provider == provider
                and row.connection_id == connection_id

            ),
            None,
        )

    async def list(self, user_id, provider, project_id=""):
        return [
            row
            for row in self.rows
            if row.user_id == user_id and row.provider == provider
        ]

    def add(self, connection):
        self.rows.append(connection)

    async def commit(self):
        self.commits += 1

    async def refresh(self, connection):
        return None


class FakeZentaoAuthProvider:
    def __init__(self, token="token-1"):
        self.token = token
        self.calls = []

    async def authenticate(self, base_url, account, password):
        self.calls.append((base_url, account, password))
        return SimpleNamespace(access_token=self.token, expires_at=None)


class FakeZentaoAuthHttpClient:
    kwargs = {}

    def __init__(self, **kwargs):
        self.__class__.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url, json):
        return SimpleNamespace(
            status_code=200,
            text='{"token":"token-ssl"}',
            json=lambda: {"token": "token-ssl"},
        )


@pytest.mark.asyncio
async def test_zentao_auth_provider_disables_ssl_verification(monkeypatch):
    monkeypatch.setattr(
        "testing_agent.services.zentao_auth.httpx.AsyncClient",
        FakeZentaoAuthHttpClient,
    )

    result = await ZentaoAuthProvider().authenticate(
        "https://zentao.example",
        "tester",
        "secret",
    )

    assert result.access_token == "token-ssl"
    assert FakeZentaoAuthHttpClient.kwargs["verify"] is False


@pytest.mark.asyncio
async def test_create_zentao_connection_authenticates_and_stores_token(monkeypatch):
    ids = iter(["connection-1"])
    monkeypatch.setattr("testing_agent.services.integration_connection.new_id", lambda: next(ids))
    repository = FakeIntegrationRepositoryForConnectionAuth()
    auth_provider = FakeZentaoAuthProvider()
    service = IntegrationConnectionService(
        repository,
        zentao_auth_provider=auth_provider,
        credential_cipher=IntegrationCredentialCipher("test-key"),
    )

    result = await service.create(
        "zentao",
        {
            "name": "公司禅道",
            "baseUrl": "https://zentao.example",
            "account": "tester",
            "password": "secret",
        },
        "user-1",
    )

    assert auth_provider.calls == [("https://zentao.example", "tester", "secret")]
    assert repository.rows[0].access_token == "token-1"
    assert repository.rows[0].auth_type == "account_password"
    assert repository.rows[0].last_auth_at is not None
    assert result["connectionId"] == "connection-1"
    assert result["hasAccessToken"] is True


@pytest.mark.asyncio
async def test_integration_connections_are_scoped_by_project(monkeypatch):
    ids = iter(["connection-1"])
    monkeypatch.setattr("testing_agent.services.integration_connection.new_id", lambda: next(ids))
    repository = FakeIntegrationRepositoryForConnectionAuth()
    repository.project = SimpleNamespace(project_id="project-1", user_id="user-1")

    async def get_project(project_id):
        assert project_id == "project-1"
        return repository.project

    async def scoped_list(user_id, provider, project_id=""):
        return [
            row
            for row in repository.rows
            if row.user_id == user_id
            and row.provider == provider
            and row.project_id == project_id

        ]

    repository.get_project = get_project
    repository.list = scoped_list
    service = IntegrationConnectionService(
        repository, credential_cipher=IntegrationCredentialCipher("test-key")
    )

    result = await service.create(
        "llm",
        {
            "name": "LLM",
            "baseUrl": "https://llm.example",
            "modelId": "gpt",
            "apiKey": "key",
        },
        "user-1",
        "project-1",
    )
    repository.rows.append(
        SimpleNamespace(
            connection_id="connection-other",
            project_id="project-2",
            user_id="user-1",
            provider="llm",
            name="Other",
        )
    )

    listed = await service.list("llm", "user-1", "project-1")

    assert result["projectId"] == "project-1"
    assert repository.rows[0].project_id == "project-1"
    assert [item["connectionId"] for item in listed["items"]] == ["connection-1"]


@pytest.mark.asyncio
async def test_project_zentao_binding_uses_go_request_and_updates_project_summary(
    monkeypatch,
):
    ids = iter(["binding-1"])
    monkeypatch.setattr("testing_agent.services.resource_binding.new_id", lambda: next(ids))
    repository = FakeResourceBindingRepository()
    zentao_client = FakeZentaoResourceClient()
    service = ResourceBindingService(
        repository,
        FakeIntegrationConnectionService(),
        zentao_client,
    )

    result = await service.create(
        "project",
        "project-1",
        {
            "provider": "zentao",
            "connectionId": "conn-1",
            "remoteResourceId": "101",
        },
        "user-1",
    )

    binding = repository.rows[0]
    assert result["bindingId"] == "binding-1"
    assert result["remoteResourceType"] == "project"
    assert result["remoteResourceId"] == "101"
    assert result["remoteNameSnapshot"] == "旧禅道项目"
    assert result["lastVerifiedAt"] is not None
    assert binding.remote_parent_id == ""
    assert binding.extra_json == {}
    assert zentao_client.project_calls == [("conn-1", "101")]
    assert repository.committed is True
    assert repository.refreshed is binding


@pytest.mark.asyncio
async def test_project_zentao_binding_rejects_existing_active_local_binding():
    repository = FakeResourceBindingRepository()
    repository.active_local = SimpleNamespace(binding_id="existing")
    service = ResourceBindingService(
        repository,
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(),
    )

    with pytest.raises(type(ErrResourceBindingAlreadyExists)) as exc_info:
        await service.create(
            "project",
            "project-1",
            {
                "provider": "zentao",
                "connectionId": "conn-1",
                "remoteResourceId": "101",
            },
            "user-1",
        )

    assert exc_info.value.code == ErrResourceBindingAlreadyExists.code


@pytest.mark.asyncio
async def test_project_zentao_binding_rejects_existing_active_remote_binding():
    repository = FakeResourceBindingRepository()
    repository.remote_exists = True
    service = ResourceBindingService(
        repository,
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(),
    )

    with pytest.raises(type(ErrRemoteResourceAlreadyBound)) as exc_info:
        await service.create(
            "project",
            "project-1",
            {
                "provider": "zentao",
                "connectionId": "conn-1",
                "remoteResourceId": "101",
            },
            "user-1",
        )

    assert exc_info.value.code == ErrRemoteResourceAlreadyBound.code


@pytest.mark.asyncio
async def test_project_zentao_binding_rejects_deleted_remote_project():
    repository = FakeResourceBindingRepository()
    service = ResourceBindingService(
        repository,
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(deleted=True),
    )

    with pytest.raises(type(ErrZentaoRemoteResourceUnavailable)) as exc_info:
        await service.create(
            "project",
            "project-1",
            {
                "provider": "zentao",
                "connectionId": "conn-1",
                "remoteResourceId": "101",
            },
            "user-1",
        )

    assert exc_info.value.code == ErrZentaoRemoteResourceUnavailable.code
    assert "已删除" in exc_info.value.message


@pytest.mark.asyncio
async def test_zentao_candidate_lists_are_loaded_from_remote_client():
    client = FakeZentaoBrowseClient()
    service = IntegrationConnectionService(
        FakeIntegrationRepositoryForZentaoBrowse(),
        client,
    )

    projects = await service.list_zentao_projects("conn-1", "user-1", page=2, page_size=50)
    executions = await service.list_zentao_project_executions(
        "conn-1",
        "101",
        "user-1",
        page=3,
        page_size=40,
    )
    testtasks = await service.list_zentao_execution_testtasks(
        "conn-1",
        "201",
        "user-1",
        page=4,
        page_size=30,
    )
    stories = await service.list_zentao_execution_stories("conn-1", "201", "user-1")
    cases = await service.list_zentao_execution_cases(
        "conn-1",
        "201",
        "user-1",
        page=5,
        page_size=20,
    )

    assert projects == {
        "connectionId": "conn-1",
        "items": [
            {
                "id": 101,
                "name": "项目A",
                "code": "PA",
                "description": "desc",
                "status": "doing",
                "begin": "2026-01-01",
                "end": "2026-02-01",
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-02T00:00:00Z",
            }
        ],
        "total": 2,
    }
    assert executions["items"] == [
        {
            "id": 201,
            "projectId": 101,
            "name": "执行A",
            "description": "exec desc",
            "status": "doing",
            "begin": "2026-01-03",
            "end": "2026-01-20",
            "createdAt": "",
            "updatedAt": "",
        }
    ]
    assert executions["remoteProjectId"] == "101"
    assert testtasks["items"][0]["executionId"] == 201
    assert testtasks["items"][0]["title"] == "测试单标题"
    assert stories["items"][0]["title"] == "需求A"
    assert stories["items"][0]["productId"] == 1
    assert cases["items"][0]["title"] == "用例A"
    assert cases["items"][0]["expectedResults"] == "预期"
    assert client.calls == [
        ("projects", "conn-1", 2, 50),
        ("executions", "conn-1", "101", 3, 40),
        ("testtasks", "conn-1", "201", 4, 30),
        ("stories", "conn-1", "201"),
        ("cases", "conn-1", "201", 5, 20),
    ]


@pytest.mark.asyncio
async def test_read_import_payload_accepts_uploaded_yaml_file():
    payload = await api_collection.read_import_payload(
        None,
        FakeUpload(b"cases:\n  - name: imported\n    method: POST\n"),
    )

    assert payload == {"cases": [{"name": "imported", "method": "POST"}]}


@pytest.mark.asyncio
async def test_api_collection_import_creates_go_extract_and_assert_rules(monkeypatch):
    class FakeApiCollectionRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []

        async def get_collection(self, collection_id):
            assert collection_id == "collection-1"
            return SimpleNamespace(collection_id="collection-1", requirement_id="requirement-1")

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(sprint_id="sprint-1")

        async def get_sprint(self, sprint_id):
            assert sprint_id == "sprint-1"
            return SimpleNamespace(project_id="project-1")

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(user_id="user-1", project_id="project-1")

        async def exists_case_by_collection_and_name(self, collection_id, name):
            return False

        def add(self, row):
            self.rows.append(row)

        async def commit(self):
            return None

    ids = iter(["case-1", "extract-1", "assert-1"])
    monkeypatch.setattr(api_collection, "new_id", lambda: next(ids))
    repository = FakeApiCollectionRepository()
    service = api_collection.ApiCollectionService(repository)
    payload = {
        "cases": [
            {
                "name": "imported",
                "method": "GET",
                "urlTemplate": "/ping",
                "extractRules": [
                    {
                        "name": "token",
                        "source": "body_jsonpath",
                        "sourceExpr": "$.token",
                        "varKey": "token",
                    }
                ],
                "assertRules": [
                    {
                        "name": "ok",
                        "assertSource": "status_code",
                        "comparator": "eq",
                        "expectedValue": "200",
                    }
                ],
            }
        ]
    }

    result = await service.import_cases("user-1", "collection-1", payload, None)

    api_case = next(row for row in repository.rows if isinstance(row, ApiCase))
    extract_rule = next(row for row in repository.rows if isinstance(row, ApiExtractRule))
    assert_rule = next(row for row in repository.rows if isinstance(row, ApiAssertRule))
    assert result == {
        "collectionId": "collection-1",
        "importedCaseCount": 1,
        "importedExtractRuleCount": 1,
        "importedAssertRuleCount": 1,
    }
    assert api_case.case_id == "case-1"
    assert extract_rule.extract_rule_id == "extract-1"
    assert extract_rule.case_id == "case-1"
    assert assert_rule.assert_rule_id == "assert-1"
    assert assert_rule.case_id == "case-1"


@pytest.mark.asyncio
async def test_api_collection_import_accepts_go_generated_yaml_sample(monkeypatch):
    class FakeApiCollectionRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []

        async def get_collection(self, collection_id):
            assert collection_id == "collection-1"
            return SimpleNamespace(collection_id="collection-1", requirement_id="requirement-1")

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

        async def commit(self):
            return None

    ids = iter([f"id-{index}" for index in range(1, 40)])
    monkeypatch.setattr(api_collection, "new_id", lambda: next(ids))
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
            return SimpleNamespace(collection_id="collection-1", requirement_id="requirement-1")

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


def test_llm_credentials_payload_uses_stored_connection_secrets():
    connection = SimpleNamespace(
        connection_id="conn-1",
        base_url="https://llm.example",
        access_token="access-token",
        secret_json={"apiKey": "secret-key", "modelId": "gpt-test"},
        extra_json={"organization": "org-1"},
    )

    assert worker.llm_credentials_payload("task-1", connection) == {
        "taskId": "task-1",
        "connectionId": "conn-1",
        "baseUrl": "https://llm.example",
        "modelId": "gpt-test",
        "apiKey": "secret-key",
        "organization": "org-1",
    }


@pytest.mark.asyncio
async def test_update_llm_connection_model_id_replaces_json_payload_for_persistence():
    original_extra = {"modelId": "old-model"}
    connection = SimpleNamespace(
        connection_id="conn-1",
        user_id="user-1",
        provider="llm",
        name="LLM",
        base_url="https://llm.example",
        auth_type="api_key",
        account="",
        secret_json={"apiKey": "key"},
        access_token="key",
        status="active",
        extra_json=original_extra,
        last_auth_at=None,
        last_auth_error="",
        token_expires_at=None,
        created_at=None,
        updated_at=None,
    )

    from unittest.mock import AsyncMock

    class FakeRepository:
        session = SimpleNamespace(scalar=AsyncMock(return_value=None))

        async def get(self, user_id, provider, connection_id, project_id=""):
            assert user_id == "user-1"
            assert provider == "llm"
            assert connection_id == "conn-1"
            return connection

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    service = IntegrationConnectionService(FakeRepository())

    payload = await service.update(
        "llm",
        "conn-1",
        {"modelId": "new-model"},
        "user-1",
    )

    assert payload["modelId"] == "new-model"
    assert connection.extra_json == {"modelId": "new-model"}
    assert connection.extra_json is not original_extra
    assert original_extra == {"modelId": "old-model"}


def test_apply_ai_completion_to_run_persists_result_fields():
    run = SimpleNamespace(
        status="running",
        current_stage="generating",
        stage_status="running",
        snapshot_json={},
        error_message="",
        result_yaml="",
        result_summary_json={},
        duration_ms=0,
        finished_at=None,
    )
    body = WorkerTaskEventRequest(
        workerId="worker-1",
        status="success",
        snapshotJson={
            "currentStage": "completed",
            "stageStatus": "completed",
            "resultYaml": "cases: []",
            "resultSummaryJson": {"total": 0},
        },
        durationMs=123,
    )

    worker.apply_ai_completion_to_run(run, body)

    assert run.status == "success"
    assert run.current_stage == "completed"
    assert run.stage_status == "completed"
    assert run.result_yaml == "cases: []"
    assert run.result_summary_json == {"total": 0}
    assert run.duration_ms == 123
    assert run.finished_at is not None


def test_ai_review_extracts_api_cases_from_result_yaml():
    run = SimpleNamespace(
        result_yaml="cases:\n  - name: generated\n    method: GET\n    url: /ping\n"
    )

    cases = ai_tasks.generated_api_cases(run)

    assert cases == [{"name": "generated", "method": "GET", "url": "/ping"}]


@pytest.mark.asyncio
async def test_ai_review_imports_go_api_collection_rules_from_result_yaml(monkeypatch):
    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []

        async def get_collection(self, collection_id):
            assert collection_id == "collection-1"
            return SimpleNamespace(requirement_id="requirement-1")

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(sprint_id="sprint-1")

        async def get_sprint(self, sprint_id):
            assert sprint_id == "sprint-1"
            return SimpleNamespace(project_id="project-1")

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(user_id="user-1", project_id="project-1")

        async def exists_case_by_collection_and_name(self, collection_id, name):
            return False

        def add(self, row):
            self.rows.append(row)

    ids = iter(["case-1", "extract-1", "assert-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)
    run = SimpleNamespace(
        result_yaml=(
            "cases:\n"
            "  - name: generated\n"
            "    method: GET\n"
            "    urlTemplate: /ping\n"
            "    extractRules:\n"
            "      - name: token\n"
            "        source: body_jsonpath\n"
            "        sourceExpr: $.token\n"
            "        varKey: token\n"
            "    assertRules:\n"
            "      - name: ok\n"
            "        assertSource: status_code\n"
            "        comparator: eq\n"
            "        expectedValue: '200'\n"
        )
    )

    await service.import_generated_api_cases("user-1", run, "collection-1")

    api_case = next(row for row in repository.rows if isinstance(row, ApiCase))
    extract_rule = next(row for row in repository.rows if isinstance(row, ApiExtractRule))
    assert_rule = next(row for row in repository.rows if isinstance(row, ApiAssertRule))
    assert api_case.case_id == "case-1"
    assert extract_rule.extract_rule_id == "extract-1"
    assert extract_rule.case_id == "case-1"
    assert extract_rule.source == "body_jsonpath"
    assert extract_rule.source_expr == "$.token"
    assert extract_rule.var_key == "token"
    assert assert_rule.assert_rule_id == "assert-1"
    assert assert_rule.case_id == "case-1"
    assert assert_rule.assert_source == "status_code"
    assert assert_rule.comparator == "eq"


@pytest.mark.asyncio
async def test_ai_review_rejects_non_terminal_runs_like_go():
    class FakeRepository(AuthorizedRepositoryFixture):
        def __init__(self):
            self.run = SimpleNamespace(
                run_id="run-1",
                task_id="task-1",
                project_id="project-1",
                status="running",
                review_status="pending",
            )

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return self.run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="api_case_generate",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def commit(self):
            raise AssertionError("non-terminal runs should be rejected before commit")

    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    with pytest.raises(type(ErrBadRequest)):
        await service.review("api", "run-1", {"action": "reject"}, "user-1")


def test_ai_review_extracts_function_suites_from_result_yaml():
    run = SimpleNamespace(
        result_yaml=(
            "suites:\n"
            "  - name: 登录\n"
            "    cases:\n"
            "      - title: 成功登录\n"
            "        steps: 输入账号\n"
            "        expectedResults: 进入首页\n"
        )
    )

    suites = ai_tasks.generated_function_suites(run)

    assert suites == [
        {
            "name": "登录",
            "cases": [
                {
                    "title": "成功登录",
                    "steps": "输入账号",
                    "expectedResults": "进入首页",
                }
            ],
        }
    ]


def test_requirement_analysis_kind_maps_to_requirement_analysis_task_type():
    assert ai_tasks.task_type_for("function") == "functional_case_generate"
    assert ai_tasks.task_type_for("requirement_analysis") == "requirement_analysis"


def test_requirement_analysis_stage_requests_accept_result_yaml_for_openapi_contract():
    run_request = RequirementAnalysisRunRequest(resultYaml="final yaml")
    review_request = AiGenerateTaskReviewRequest(resultYaml="final yaml")

    assert run_request.result_yaml == "final yaml"
    assert run_request.model_dump(by_alias=True, exclude_none=True)["resultYaml"] == "final yaml"
    assert review_request.result_yaml == "final yaml"
    assert review_request.model_dump(by_alias=True, exclude_none=True)["resultYaml"] == "final yaml"


@pytest.mark.asyncio
async def test_requirement_analysis_create_requires_requirement_id():
    class FakeRepository:
        session = AuthorizationDatabase()

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        def add(self, row):
            raise AssertionError("task should not be created without requirementId")

        async def commit(self):
            raise AssertionError("task should not commit without requirementId")

        async def refresh(self, row):
            raise AssertionError("task should not refresh without requirementId")

    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    with pytest.raises(type(ErrBadRequest)):
        await service.create(
            "requirement_analysis",
            "project-1",
            {"name": "Analyze requirement"},
            "user-1",
        )


@pytest.mark.asyncio
async def test_api_generate_run_snapshot_uses_task_source():
    class FakeRepository:
        async def get_requirement(self, requirement_id):
            raise AssertionError("API generation should not load requirement document")

    task = SimpleNamespace(
        task_id="task-1",
        task_type="api_case_generate",
        name="Generate API cases",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="text",
        source_content="api source",
        instruction="cover APIs",
    )

    snapshot = await ai_tasks.build_generate_run_snapshot(FakeRepository(), "api", task, "run-1")

    assert snapshot == {
        "taskId": "task-1",
        "runId": "run-1",
        "taskType": "api_case_generate",
        "name": "Generate API cases",
        "projectId": "project-1",
        "sprintId": "sprint-1",
        "requirementId": "requirement-1",
        "sourceType": "text",
        "sourceContent": "api source",
        "instruction": "cover APIs",
    }


@pytest.mark.asyncio
async def test_ai_generate_run_uses_go_connection_id_for_worker_task(monkeypatch):
    class FakeRepository(AuthorizedRepositoryFixture):
        def __init__(self):
            self.rows = []

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="api_case_generate",
                name="Generate API cases",
                project_id="project-1",
                sprint_id="sprint-1",
                requirement_id="requirement-1",
                creator_user_id="user-1",
                source_type="text",
                source_content="api source",
                instruction="cover APIs",
            )

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    ids = iter(["run-1", "worker-task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    await service.run("api", "task-1", {"connectionId": "conn-1"}, "user-1")

    worker_task = next(row for row in repository.rows if hasattr(row, "llm_connection_id"))
    assert worker_task.llm_connection_id == "conn-1"


@pytest.mark.asyncio
async def test_function_checkpoint_run_starts_at_requirement_analysis(monkeypatch):
    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="functional_case_generate",
                name="Generate function cases",
                project_id="project-1",
                sprint_id="sprint-1",
                requirement_id="requirement-1",
                creator_user_id="user-1",
                source_type="text",
                source_content="task source",
                instruction="cover functions",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_integration_connection(self, connection_id):
            assert connection_id == "conn-1"
            return SimpleNamespace(connection_id="conn-1")

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="text",
                document_content="requirement source",
                document_storage_path="",
            )

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    ids = iter(["run-1", "worker-task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    await service.run(
        "function",
        "task-1",
        {"connectionId": "conn-1", "checkpointEnabled": True},
        "user-1",
    )

    run = next(row for row in repository.rows if hasattr(row, "checkpoint_enabled"))
    assert run.current_stage == "requirement_analysis"
    assert run.stage_status == "pending"


@pytest.mark.asyncio
async def test_ai_generate_run_requires_go_connection_id():
    class FakeRepository(AuthorizedRepositoryFixture):
        async def get_task(self, task_id):
            return SimpleNamespace(
                task_id="task-1",
                task_type="api_case_generate",
                name="Generate API cases",
                project_id="project-1",
                sprint_id="sprint-1",
                requirement_id="requirement-1",
                creator_user_id="user-1",
                source_type="text",
                source_content="api source",
                instruction="cover APIs",
            )

        def add_all(self, rows):
            raise AssertionError("run should reject missing connectionId before creating rows")

        async def commit(self):
            raise AssertionError("run should reject missing connectionId before committing")

    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    with pytest.raises(type(ErrBadRequest)):
        await service.run("api", "task-1", {}, "user-1")


@pytest.mark.asyncio
async def test_function_generate_run_snapshot_uses_requirement_document():
    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="docx",
                document_content="# requirement doc",
                document_download_url="/v1/requirements/requirement-1/download",
            )

    task = SimpleNamespace(
        task_id="task-1",
        task_type="functional_case_generate",
        name="Generate function cases",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="manual",
        source_content="task source should not be used",
        instruction="cover functions",
    )

    snapshot = await ai_tasks.build_generate_run_snapshot(
        FakeRepository(), "function", task, "run-1", worker_task_id="worker-task-1"
    )

    assert "sourceType" not in snapshot
    assert snapshot["documentType"] == "docx"
    assert snapshot["documentDownloadUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )
    assert snapshot["sourceContent"] == "# requirement doc"
    assert snapshot["taskType"] == "functional_case_generate"


@pytest.mark.asyncio
async def test_function_generate_run_snapshot_rejects_original_requirement_source_file(tmp_path):
    source_path = tmp_path / "requirement.txt"
    source_path.write_text("requirement source from file", encoding="utf-8")

    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="text",
                document_content="",
                document_storage_path=str(source_path),
                document_download_url="/v1/requirements/requirement-1/download",
            )

    task = SimpleNamespace(
        task_id="task-1",
        task_type="functional_case_generate",
        name="Generate function cases",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="manual",
        source_content="task source should not be used",
        instruction="cover functions",
    )

    with pytest.raises(type(ErrBadRequest), match="请先完成需求分析并导入增强文本"):
        await ai_tasks.build_generate_run_snapshot(
            FakeRepository(), "function", task, "run-1", worker_task_id="worker-task-1"
        )


@pytest.mark.asyncio
async def test_function_generate_run_snapshot_prefers_document_content_over_source_file(
    tmp_path,
):
    source_path = tmp_path / "requirement.txt"
    source_path.write_text("old requirement source from file", encoding="utf-8")

    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="text",
                document_content="reviewed requirement content",
                document_storage_path=str(source_path),
                document_download_url="/v1/requirements/requirement-1/download",
            )

    task = SimpleNamespace(
        task_id="task-1",
        task_type="functional_case_generate",
        name="Generate function cases",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="manual",
        source_content="task source should not be used",
        instruction="cover functions",
    )

    snapshot = await ai_tasks.build_generate_run_snapshot(
        FakeRepository(), "function", task, "run-1", worker_task_id="worker-task-1"
    )

    assert snapshot["documentType"] == "text"
    assert snapshot["sourceContent"] == "reviewed requirement content"


@pytest.mark.asyncio
async def test_requirement_analysis_snapshot_prefers_document_content_for_docx_with_file():
    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="docx",
                document_content="reviewed docx requirement content",
                document_storage_path="storage/requirements/requirement-1/requirement.docx",
                document_download_url="/v1/requirements/requirement-1/download",
            )

    task = SimpleNamespace(
        task_id="task-1",
        task_type="requirement_analysis",
        name="Analyze requirement",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="manual",
        source_content="task source should not be used",
        instruction="find ambiguities",
    )

    snapshot = await ai_tasks.build_generate_run_snapshot(
        FakeRepository(), "requirement_analysis", task, "run-1", worker_task_id="worker-task-1"
    )

    assert snapshot["documentType"] == "docx"
    assert snapshot["documentDownloadUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )
    assert snapshot["sourceContent"] == "reviewed docx requirement content"


@pytest.mark.asyncio
async def test_requirement_analysis_snapshot_uses_docx_download_url_when_document_content_empty():
    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="docx",
                document_content="",
                document_storage_path="storage/requirements/requirement-1/requirement.docx",
                document_download_url="/v1/requirements/requirement-1/download",
            )

    task = SimpleNamespace(
        task_id="task-1",
        task_type="requirement_analysis",
        name="Analyze requirement",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="manual",
        source_content="task source should not be used",
        instruction="find ambiguities",
    )

    snapshot = await ai_tasks.build_generate_run_snapshot(
        FakeRepository(), "requirement_analysis", task, "run-1", worker_task_id="worker-task-1"
    )

    assert snapshot["documentType"] == "docx"
    assert snapshot["documentDownloadUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )
    assert snapshot["sourceContent"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )


@pytest.mark.asyncio
async def test_requirement_analysis_run_snapshot_uses_requirement_document():
    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="word",
                document_content="requirement document from saved requirement",
                document_download_url="/v1/requirements/requirement-1/download",
            )

    task = SimpleNamespace(
        task_id="task-1",
        task_type="requirement_analysis",
        name="Analyze requirement",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="manual",
        source_content="task source should not be used",
        instruction="find ambiguities",
    )

    snapshot = await ai_tasks.build_generate_run_snapshot(
        FakeRepository(), "requirement_analysis", task, "run-1", worker_task_id="worker-task-1"
    )

    assert "sourceType" not in snapshot
    assert snapshot["documentType"] == "docx"
    assert snapshot["documentDownloadUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )
    assert snapshot["sourceContent"] == "requirement document from saved requirement"
    assert snapshot["taskType"] == "requirement_analysis"


@pytest.mark.asyncio
async def test_requirement_analysis_run_enqueues_requirement_analysis_worker_task(monkeypatch):
    class FakeRepository(AuthorizedRepositoryFixture):
        def __init__(self):
            self.rows = []

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                name="Analyze requirement",
                project_id="project-1",
                sprint_id="sprint-1",
                requirement_id="requirement-1",
                creator_user_id="user-1",
                source_type="manual",
                source_content="task source should not be used",
                instruction="find ambiguities",
            )

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="text",
                document_content="saved requirement text",
                document_download_url="/v1/requirements/requirement-1/download",
            )

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    ids = iter(["run-1", "worker-task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    await service.run("requirement_analysis", "task-1", {"connectionId": "conn-1"}, "user-1")

    worker_task = next(row for row in repository.rows if hasattr(row, "llm_connection_id"))
    run = next(row for row in repository.rows if hasattr(row, "snapshot_json"))
    assert worker_task.task_type == "requirement_analysis"
    assert "sourceType" not in run.snapshot_json
    assert run.snapshot_json["documentType"] == "text"
    assert run.snapshot_json["documentDownloadUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )
    assert run.snapshot_json["sourceContent"] == "saved requirement text"


@pytest.mark.asyncio
async def test_requirement_analysis_task_create_persists_task_without_running(monkeypatch):
    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []
            self.task = None

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
                name="Login requirement",
                document_type="text",
                document_content="saved requirement text",
            )

        async def get_sprint(self, sprint_id):
            assert sprint_id == "sprint-1"
            return SimpleNamespace(sprint_id="sprint-1", project_id="project-1")

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        def add(self, row):
            self.task = row
            self.rows.append(row)

        def add_all(self, rows):
            raise AssertionError("creating a requirement analysis task should not create runs")

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    ids = iter(["task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    payload = await service.create(
        "requirement_analysis",
        "project-1",
        {"requirementId": "requirement-1", "instruction": "find ambiguity"},
        "user-1",
    )

    assert payload["taskId"] == "task-1"
    assert payload["taskType"] == "requirement_analysis"
    assert payload["name"] == "Login requirement analysis"
    assert repository.task.source_type == "text"
    assert repository.task.source_content == "saved requirement text"
    assert repository.task.instruction == "find ambiguity"
    assert len(repository.rows) == 1


@pytest.mark.asyncio
async def test_requirement_analysis_run_requires_connection_id():
    class FakeRepository:
        session = AuthorizationDatabase()

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                name="Analyze requirement",
                project_id="project-1",
                sprint_id="sprint-1",
                requirement_id="requirement-1",
                creator_user_id="user-1",
                source_type="manual",
                source_content="task source should not be used",
                instruction="find ambiguity",
            )

        async def get_project(self, project_id):
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        def add_all(self, rows):
            raise AssertionError("run should reject missing connectionId before creating rows")

        async def commit(self):
            raise AssertionError("run should reject missing connectionId before committing")

    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    with pytest.raises(type(ErrBadRequest)):
        await service.run("requirement_analysis", "task-1", {}, "user-1")


@pytest.mark.asyncio
async def test_requirement_analysis_list_runs_uses_task_scope():
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        checkpoint_enabled=False,
        current_stage="completed",
        stage_status="completed",
        snapshot_json={},
        error_message="",
        config_json={},
        result_yaml="analysis: ok",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=10,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def list_runs(self, task_id):
            assert task_id == "task-1"
            return [run]

    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    payload = await service.list_runs("requirement_analysis", "task-1", "user-1")

    assert payload == {"total": 1, "items": [ai_tasks.dump_run(run)]}


@pytest.mark.asyncio
async def test_requirement_analysis_run_import_writes_result_to_requirement_document_content():
    requirement = SimpleNamespace(
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        name="Login requirement",
        document_type="text",
        document_content="",
        document_filename="requirement.txt",
        document_hash="hash",
        document_download_url="/v1/requirements/requirement-1/download",
        created_at="",
        updated_at="",
    )
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        checkpoint_enabled=False,
        current_stage="completed",
        stage_status="completed",
        snapshot_json={},
        error_message="",
        config_json={},
        result_yaml="analysis: ok",
        result_summary_json={"summary": "fallback"},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
        finished_at=None,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.committed = False
            self.refreshed = None

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return requirement

        async def get_sprint(self, sprint_id):
            assert sprint_id == "sprint-1"
            return SimpleNamespace(sprint_id="sprint-1", project_id="project-1")

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def commit(self):
            self.committed = True

        async def refresh(self, row):
            self.refreshed = row

    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    payload = await service.import_requirement_analysis_run("run-1", "user-1")

    assert requirement.document_content == "analysis: ok"
    assert payload["documentContent"] == "analysis: ok"
    assert repository.committed is True
    assert repository.refreshed is requirement


def test_requirement_analysis_run_import_endpoint_delegates_to_service():
    class FakeAiGenerateTaskService:
        async def import_requirement_analysis_run(self, run_id, user_id):
            assert run_id == "run-1"
            assert user_id == "user-1"
            return {
                "requirementId": "requirement-1",
                "sprintId": "sprint-1",
                "name": "Login requirement",
                "documentType": "text",
                "documentContent": "analysis: ok",
                "documentFilename": "requirement.txt",
                "documentHash": "hash",
                "documentDownloadUrl": "/v1/requirements/requirement-1/download",
                "createdAt": "",
                "updatedAt": "",
            }

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: FakeAiGenerateTaskService()
    client = TestClient(app)

    response = client.post("/v1/requirement-analysis-runs/run-1/import-to-requirement")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["documentContent"] == "analysis: ok"


@pytest.mark.asyncio
async def test_requirement_analysis_checkpoint_run_starts_extracting_text(monkeypatch):
    task = SimpleNamespace(
        task_id="task-1",
        task_type="requirement_analysis",
        name="Analyze requirement",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        creator_user_id="user-1",
        source_type="text",
        source_content="raw requirement",
        instruction="",
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return task

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
                document_type="text",
                document_content="raw requirement",
                document_storage_path="",
                document_download_url="",
            )

        async def get_sprint(self, sprint_id):
            assert sprint_id == "sprint-1"
            return SimpleNamespace(sprint_id="sprint-1", project_id="project-1")

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    ids = iter(["run-1", "worker-task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    payload = await service.run(
        "requirement_analysis",
        "task-1",
        {
            "connectionId": "connection-1",
            "checkpointEnabled": True,
            "configJson": "{}",
        },
        "user-1",
    )

    assert payload["checkpointEnabled"] is True
    assert payload["currentStage"] == "extracting_text"
    assert payload["stageStatus"] == "pending"
    assert payload["configJson"] == {}


@pytest.mark.asyncio
async def test_requirement_analysis_run_defaults_to_checkpoint(monkeypatch):
    task = SimpleNamespace(
        task_id="task-1",
        task_type="requirement_analysis",
        name="Analyze requirement",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        creator_user_id="user-1",
        source_type="text",
        source_content="raw requirement",
        instruction="",
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return task

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
                document_type="text",
                document_content="raw requirement",
                document_storage_path="",
                document_download_url="",
            )

        async def get_sprint(self, sprint_id):
            assert sprint_id == "sprint-1"
            return SimpleNamespace(sprint_id="sprint-1", project_id="project-1")

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    ids = iter(["run-1", "worker-task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    payload = await service.run(
        "requirement_analysis",
        "task-1",
        {"connectionId": "connection-1"},
        "user-1",
    )

    assert payload["checkpointEnabled"] is True
    assert payload["currentStage"] == "extracting_text"
    assert payload["stageStatus"] == "pending"


@pytest.mark.asyncio
async def test_requirement_analysis_run_ignores_false_checkpoint_flag(monkeypatch):
    task = SimpleNamespace(
        task_id="task-1",
        task_type="requirement_analysis",
        name="Analyze requirement",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        creator_user_id="user-1",
        source_type="text",
        source_content="raw requirement",
        instruction="",
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return task

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
                document_type="text",
                document_content="raw requirement",
                document_storage_path="",
                document_download_url="",
            )

        async def get_sprint(self, sprint_id):
            assert sprint_id == "sprint-1"
            return SimpleNamespace(sprint_id="sprint-1", project_id="project-1")

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    ids = iter(["run-1", "worker-task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    payload = await service.run(
        "requirement_analysis",
        "task-1",
        {"connectionId": "connection-1", "checkpointEnabled": False},
        "user-1",
    )

    assert payload["checkpointEnabled"] is True
    assert payload["currentStage"] == "extracting_text"
    assert payload["stageStatus"] == "pending"


@pytest.mark.asyncio
async def test_requirement_analysis_review_extracting_text_enqueues_writing_requirement(
    monkeypatch,
):
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="waiting_review",
        checkpoint_enabled=True,
        current_stage="extracting_text",
        stage_status="waiting_review",
        snapshot_json={},
        error_message="",
        config_json={"firstStepOutput": "raw text"},
        result_yaml="",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.added = []

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_latest_worker_task_by_run_id(self, run_id):
            assert run_id == "run-1"
            return SimpleNamespace(llm_connection_id="connection-1")

        def add(self, row):
            self.added.append(row)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    monkeypatch.setattr(ai_tasks, "new_id", lambda: "worker-task-next")
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    payload = await service.review_requirement_analysis_stage(
        "run-1",
        {
            "stage": "extracting_text",
            "action": "approve",
            "configJson": '{"firstStepOutput":"reviewed text"}',
        },
        "user-1",
    )

    assert payload["status"] == "pending"
    assert payload["currentStage"] == "writing_requirement"
    assert payload["stageStatus"] == "pending"
    assert payload["configJson"] == {"firstStepOutput": "reviewed text"}
    assert len(repository.added) == 1
    worker_task = repository.added[0]
    assert worker_task.task_type == "requirement_analysis"
    assert worker_task.run_id == "run-1"
    assert worker_task.llm_connection_id == "connection-1"


@pytest.mark.asyncio
async def test_requirement_analysis_revise_extracting_text_enqueues_same_stage_worker_task(
    monkeypatch,
):
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="waiting_review",
        checkpoint_enabled=True,
        current_stage="extracting_text",
        stage_status="waiting_review",
        snapshot_json={},
        error_message="",
        config_json={"firstStepOutput": "raw text"},
        result_yaml="",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.added = []

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_latest_worker_task_by_run_id(self, run_id):
            assert run_id == "run-1"
            return SimpleNamespace(llm_connection_id="connection-1")

        def add(self, row):
            self.added.append(row)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    monkeypatch.setattr(ai_tasks, "new_id", lambda: "worker-task-revise")
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    payload = await service.revise_requirement_analysis_stage(
        "run-1",
        {
            "stage": "extracting_text",
            "revisionInstruction": "补充图片流程和异常场景",
            "configJson": '{"firstStepOutput":"reviewed text"}',
        },
        "user-1",
    )

    assert payload["status"] == "pending"
    assert payload["currentStage"] == "extracting_text"
    assert payload["stageStatus"] == "pending"
    assert payload["configJson"] == {
        "firstStepOutput": "reviewed text",
        "revisionInstruction": "补充图片流程和异常场景",
    }
    assert len(repository.added) == 1
    worker_task = repository.added[0]
    assert worker_task.domain == "ai"
    assert worker_task.task_id == "worker-task-revise"
    assert worker_task.task_type == "requirement_analysis"
    assert worker_task.run_id == "run-1"
    assert worker_task.generate_task_id == "task-1"
    assert worker_task.llm_connection_id == "connection-1"
    assert worker_task.status == "pending"


@pytest.mark.asyncio
async def test_requirement_analysis_save_final_output_before_import():
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        checkpoint_enabled=True,
        current_stage="feature_understanding",
        stage_status="completed",
        snapshot_json={},
        error_message="",
        config_json={
            "firstStepOutput": "reviewed text",
            "secondStepOutput": "reviewed flow",
        },
        result_yaml="old final",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    payload = await service.save_requirement_analysis_stage_output(
        "run-1",
        {
            "stage": "feature_understanding",
            "resultYaml": "edited final",
            "configJson": {
                "firstStepOutput": "reviewed text",
                "secondStepOutput": "reviewed flow",
            },
        },
        "user-1",
    )

    assert payload["status"] == "success"
    assert payload["currentStage"] == "feature_understanding"
    assert payload["stageStatus"] == "completed"
    assert payload["resultYaml"] == "edited final"
    assert payload["configJson"] == {
        "firstStepOutput": "reviewed text",
        "secondStepOutput": "reviewed flow",
    }


@pytest.mark.asyncio
async def test_requirement_analysis_revise_final_output_enqueues_feature_understanding(
    monkeypatch,
):
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        checkpoint_enabled=True,
        current_stage="feature_understanding",
        stage_status="completed",
        snapshot_json={},
        error_message="",
        config_json={
            "firstStepOutput": "reviewed text",
            "secondStepOutput": "reviewed flow",
        },
        result_yaml="current final",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.added = []

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_latest_worker_task_by_run_id(self, run_id):
            assert run_id == "run-1"
            return SimpleNamespace(llm_connection_id="connection-1")

        def add(self, row):
            self.added.append(row)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    monkeypatch.setattr(ai_tasks, "new_id", lambda: "worker-task-final-revise")
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    payload = await service.revise_requirement_analysis_stage(
        "run-1",
        {
            "stage": "feature_understanding",
            "revisionInstruction": "补充验收口径",
            "resultYaml": "edited final",
            "configJson": {
                "firstStepOutput": "reviewed text",
                "secondStepOutput": "reviewed flow",
            },
        },
        "user-1",
    )

    assert payload["status"] == "pending"
    assert payload["currentStage"] == "feature_understanding"
    assert payload["stageStatus"] == "pending"
    assert payload["configJson"] == {
        "firstStepOutput": "reviewed text",
        "secondStepOutput": "reviewed flow",
        "resultYaml": "edited final",
        "revisionInstruction": "补充验收口径",
    }
    assert len(repository.added) == 1
    worker_task = repository.added[0]
    assert worker_task.task_id == "worker-task-final-revise"
    assert worker_task.task_type == "requirement_analysis"
    assert worker_task.run_id == "run-1"
    assert worker_task.llm_connection_id == "connection-1"


@pytest.mark.asyncio
async def test_requirement_analysis_save_final_output_allows_completed_stage_without_checkpoint():
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        checkpoint_enabled=False,
        current_stage="completed",
        stage_status="completed",
        snapshot_json={},
        error_message="",
        config_json={},
        result_yaml="old final",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    payload = await service.save_requirement_analysis_stage_output(
        "run-1",
        {
            "stage": "feature_understanding",
            "resultYaml": "edited final",
            "configJson": {
                "firstStepOutput": "reviewed text",
                "secondStepOutput": "reviewed flow",
            },
        },
        "user-1",
    )

    assert payload["status"] == "success"
    assert payload["currentStage"] == "completed"
    assert payload["resultYaml"] == "edited final"
    assert payload["configJson"] == {
        "firstStepOutput": "reviewed text",
        "secondStepOutput": "reviewed flow",
    }


@pytest.mark.asyncio
async def test_requirement_analysis_revise_final_output_allows_completed_stage_without_checkpoint(
    monkeypatch,
):
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        checkpoint_enabled=False,
        current_stage="completed",
        stage_status="completed",
        snapshot_json={},
        error_message="",
        config_json={},
        result_yaml="current final",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.added = []

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_latest_worker_task_by_run_id(self, run_id):
            assert run_id == "run-1"
            return SimpleNamespace(llm_connection_id="connection-1")

        def add(self, row):
            self.added.append(row)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    monkeypatch.setattr(ai_tasks, "new_id", lambda: "worker-task-final-revise")
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    payload = await service.revise_requirement_analysis_stage(
        "run-1",
        {
            "stage": "feature_understanding",
            "revisionInstruction": "补充风险点",
            "resultYaml": "edited final",
            "configJson": {
                "firstStepOutput": "reviewed text",
                "secondStepOutput": "reviewed flow",
            },
        },
        "user-1",
    )

    assert payload["status"] == "pending"
    assert payload["currentStage"] == "feature_understanding"
    assert payload["stageStatus"] == "pending"
    assert payload["configJson"] == {
        "firstStepOutput": "reviewed text",
        "secondStepOutput": "reviewed flow",
        "resultYaml": "edited final",
        "revisionInstruction": "补充风险点",
    }
    assert len(repository.added) == 1
    assert repository.added[0].task_type == "requirement_analysis"


@pytest.mark.asyncio
async def test_requirement_analysis_review_writing_requirement_enqueues_feature_understanding(
    monkeypatch,
):
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="waiting_review",
        checkpoint_enabled=True,
        current_stage="writing_requirement",
        stage_status="waiting_review",
        snapshot_json={},
        error_message="",
        config_json={
            "firstStepOutput": "reviewed text",
            "secondStepOutput": "draft flow",
        },
        result_yaml="",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.added = []

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_latest_worker_task_by_run_id(self, run_id):
            assert run_id == "run-1"
            return SimpleNamespace(llm_connection_id="connection-1")

        def add(self, row):
            self.added.append(row)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    monkeypatch.setattr(ai_tasks, "new_id", lambda: "worker-task-next")
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    payload = await service.review_requirement_analysis_stage(
        "run-1",
        {
            "stage": "writing_requirement",
            "action": "approve",
            "configJson": (
                '{"firstStepOutput":"reviewed text","secondStepOutput":"reviewed flow"}'
            ),
        },
        "user-1",
    )

    assert payload["status"] == "pending"
    assert payload["currentStage"] == "feature_understanding"
    assert payload["stageStatus"] == "pending"
    assert payload["configJson"] == {
        "firstStepOutput": "reviewed text",
        "secondStepOutput": "reviewed flow",
    }
    assert len(repository.added) == 1
    assert repository.added[0].task_type == "requirement_analysis"


@pytest.mark.asyncio
async def test_function_stage_review_approve_enqueues_next_stage_worker_task(monkeypatch):
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="waiting_review",
        checkpoint_enabled=True,
        current_stage="requirement_analysis",
        stage_status="waiting_review",
        snapshot_json={},
        error_message="",
        config_json={"requirementAnalysis": {"summary": "ok"}},
        result_yaml="",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
        started_at="started",
        finished_at="finished",
    )
    task = SimpleNamespace(
        task_id="task-1",
        task_type="functional_case_generate",
        project_id="project-1",
        creator_user_id="user-1",
    )
    latest_worker_task = SimpleNamespace(llm_connection_id="connection-1")

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.added = []
            self.committed = False
            self.refreshed = None

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return task

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_latest_worker_task_by_run_id(self, run_id):
            assert run_id == "run-1"
            return latest_worker_task

        def add(self, row):
            self.added.append(row)

        async def commit(self):
            self.committed = True

        async def refresh(self, row):
            self.refreshed = row

    monkeypatch.setattr(ai_tasks, "new_id", lambda: "worker-task-next")
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    payload = await service.review_stage(
        "run-1",
        {"action": "approve", "currentStage": "requirement_analysis"},
        "user-1",
    )

    assert payload["status"] == "pending"
    assert payload["currentStage"] == "case_names"
    assert payload["stageStatus"] == "pending"
    assert repository.committed is True
    assert repository.refreshed is run
    assert len(repository.added) == 1
    worker_task = repository.added[0]
    assert worker_task.domain == "ai"
    assert worker_task.task_id == "worker-task-next"
    assert worker_task.task_type == "functional_case_generate"
    assert worker_task.run_id == "run-1"
    assert worker_task.generate_task_id == "task-1"
    assert worker_task.llm_connection_id == "connection-1"
    assert worker_task.status == "pending"


@pytest.mark.asyncio
async def test_function_stage_review_approve_accepts_saved_waiting_review_stage(monkeypatch):
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="waiting_review",
        checkpoint_enabled=True,
        current_stage="requirement_analysis",
        stage_status="saved",
        snapshot_json={},
        error_message="",
        config_json={},
        result_yaml="",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.added = []

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="functional_case_generate",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_latest_worker_task_by_run_id(self, run_id):
            assert run_id == "run-1"
            return SimpleNamespace(llm_connection_id="connection-1")

        def add(self, row):
            self.added.append(row)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    monkeypatch.setattr(ai_tasks, "new_id", lambda: "worker-task-next")
    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    payload = await service.review_stage(
        "run-1",
        {"stage": "requirement_analysis", "action": "approve"},
        "user-1",
    )

    assert payload["status"] == "pending"
    assert payload["currentStage"] == "case_names"
    assert payload["stageStatus"] == "pending"


@pytest.mark.asyncio
async def test_save_stage_output_preserves_waiting_review_stage_status():
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="waiting_review",
        checkpoint_enabled=True,
        current_stage="requirement_analysis",
        stage_status="waiting_review",
        snapshot_json={},
        error_message="",
        config_json={},
        result_yaml="old",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="functional_case_generate",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    payload = await service.save_stage_output(
        "run-1",
        {"stage": "requirement_analysis", "configJson": {"purpose": "new"}},
        "user-1",
    )

    assert payload["stageStatus"] == "waiting_review"
    assert payload["resultYaml"] == "old"
    assert payload["configJson"]["requirementAnalysis"] == {"purpose": "new"}


def test_api_case_request_render_matches_go_worker_snapshot_contract():
    api_case = SimpleNamespace(
        method="POST",
        url_template="/users/{{userId}}",
        headers_json={"Authorization": "Bearer {{token}}"},
        query_json={"q": "{{keyword}}"},
        body_type="json",
        body_json={"name": "{{keyword}}", "active": "{{enabled}}"},
        body_text="",
        timeout_ms=3000,
    )
    environment = SimpleNamespace(base_url="https://api.example.test/v1")
    env_vars = [
        SimpleNamespace(var_key="userId", value="42"),
        SimpleNamespace(var_key="token", value="secret"),
        SimpleNamespace(var_key="keyword", value="demo"),
        SimpleNamespace(var_key="enabled", value="true"),
    ]

    rendered = render_api_case_request(api_case, environment, env_vars)

    assert rendered.snapshot == {
        "method": "POST",
        "url": "https://api.example.test/v1/users/42",
        "headersJson": '{"Authorization":"Bearer secret"}',
        "queryJson": '{"q":"demo"}',
        "bodyType": "json",
        "body": '{"name":"demo","active":"true"}',
    }
    assert rendered.runtime_vars == {
        "userId": "42",
        "token": "secret",
        "keyword": "demo",
        "enabled": "true",
    }


def test_api_case_request_template_preserves_runtime_placeholders():
    api_case = SimpleNamespace(
        method="GET",
        url_template="/profile",
        headers_json={"Authorization": "Bearer {{token}}"},
        query_json={"tenant": "{{tenant}}"},
        body_type="none",
        body_json=None,
        body_text="",
        timeout_ms=3000,
    )
    environment = SimpleNamespace(base_url="https://api.example.test/{{tenant}}")

    assert api_case_request_template(api_case, environment) == {
        "method": "GET",
        "baseUrl": "https://api.example.test/{{tenant}}",
        "urlTemplate": "/profile",
        "headersJson": '{"Authorization":"Bearer {{token}}"}',
        "queryJson": '{"tenant":"{{tenant}}"}',
        "bodyType": "none",
        "bodyJson": "",
        "bodyText": "",
        "timeoutMs": 3000,
    }


@pytest.mark.asyncio
async def test_save_extracted_environment_vars_upserts_successful_results(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = []

        async def scalar(self, statement):
            return None

        def add(self, row):
            self.added.append(row)

    session = FakeSession()
    monkeypatch.setattr(worker, "new_id", lambda: "env-var-1", raising=False)

    await worker.save_extracted_environment_vars(
        session,
        "env-1",
        [
            {"success": True, "varKey": "token", "value": "abc"},
            {"success": False, "varKey": "ignored", "value": "nope"},
            {"success": True, "varKey": "", "value": "empty"},
        ],
        actor="user-1",
    )

    assert len(session.added) == 1
    env_var = session.added[0]
    assert env_var.env_var_id == "env-var-1"
    assert env_var.environment_id == "env-1"
    assert env_var.var_key == "token"
    assert env_var.value == "abc"


@pytest.mark.asyncio
async def test_api_case_run_persists_rendered_request_snapshot():
    class FakeApiCaseRepository:
        session = AuthorizationDatabase(environment=True)

        def __init__(self):
            self.rows = []
            self.api_case = SimpleNamespace(
                case_id="case-1",
                collection_id="collection-1",
                method="GET",
                url_template="/ping/{{token}}",
                headers_json={"X-Token": "{{token}}"},
                query_json={},
                body_type="none",
                body_json=None,
                body_text="",
                timeout_ms=1000,
            )
            self.collection = SimpleNamespace(
                collection_id="collection-1",
                requirement_id="requirement-1",
            )
            self.requirement = SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
            )
            self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
            self.project = SimpleNamespace(project_id="project-1", user_id="user-1")
            self.environment = SimpleNamespace(
                environment_id="env-1",
                project_id="project-1",
                base_url="https://api.example.test",
            )

        async def get_case(self, case_id):
            return self.api_case

        async def get_collection(self, collection_id):
            return self.collection

        async def get_requirement(self, requirement_id):
            return self.requirement

        async def get_sprint(self, sprint_id):
            return self.sprint

        async def get_project(self, project_id):
            return self.project

        async def get_environment(self, environment_id):
            return self.environment

        async def list_environment_vars(self, environment_id):
            return [SimpleNamespace(var_key="token", value="abc")]

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    repository = FakeApiCaseRepository()
    service = ApiCaseService(repository)

    await service.run("user-1", "case-1", RunApiCaseRequest(environmentId="env-1"))

    run = next(row for row in repository.rows if hasattr(row, "request_snapshot_json"))
    assert run.request_snapshot_json == {
        "method": "GET",
        "url": "https://api.example.test/ping/abc",
        "headersJson": '{"X-Token":"abc"}',
        "queryJson": "{}",
        "bodyType": "none",
        "body": "",
    }
    assert run.runtime_vars_json == {"token": "abc"}


@pytest.mark.asyncio
async def test_api_case_run_response_uses_go_pending_worker_contract():
    class FakeApiCaseRepository:
        session = AuthorizationDatabase(environment=True)

        def __init__(self):
            self.rows = []
            self.api_case = SimpleNamespace(
                case_id="case-1",
                collection_id="collection-1",
                method="GET",
                url_template="/ping",
                headers_json={},
                query_json={},
                body_type="none",
                body_json=None,
                body_text="",
                timeout_ms=1000,
            )
            self.collection = SimpleNamespace(
                collection_id="collection-1",
                requirement_id="requirement-1",
            )
            self.requirement = SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
            )
            self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
            self.project = SimpleNamespace(project_id="project-1", user_id="user-1")
            self.environment = SimpleNamespace(
                environment_id="env-1",
                project_id="project-1",
                base_url="https://api.example.test",
            )

        async def get_case(self, case_id):
            return self.api_case

        async def get_collection(self, collection_id):
            return self.collection

        async def get_requirement(self, requirement_id):
            return self.requirement

        async def get_sprint(self, sprint_id):
            return self.sprint

        async def get_project(self, project_id):
            return self.project

        async def get_environment(self, environment_id):
            return self.environment

        async def list_environment_vars(self, environment_id):
            return [SimpleNamespace(var_key="token", value="abc")]

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    service = ApiCaseService(FakeApiCaseRepository())

    payload = await service.run("user-1", "case-1", RunApiCaseRequest(environmentId="env-1"))

    assert payload["status"] == "pending"
    assert payload["runtimeVarsJson"] == '{"token":"abc"}'
    assert payload["response"] == {"statusCode": 0, "headersJson": "{}", "body": ""}


@pytest.mark.asyncio
async def test_api_collection_run_response_uses_go_pending_worker_contract():
    class FakeApiCollectionRunRepository:
        session = AuthorizationDatabase(environment=True)

        def __init__(self):
            self.rows = []
            self.collection = SimpleNamespace(
                collection_id="collection-1",
                requirement_id="requirement-1",
            )
            self.requirement = SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
            )
            self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
            self.project = SimpleNamespace(project_id="project-1", user_id="user-1")
            self.environment = SimpleNamespace(
                environment_id="env-1",
                project_id="project-1",
                base_url="https://api.example.test",
            )
            self.cases = [SimpleNamespace(case_id="case-1", order_no=1, continue_on_failure=False)]

        async def get_collection(self, collection_id):
            return self.collection

        async def get_requirement(self, requirement_id):
            return self.requirement

        async def get_sprint(self, sprint_id):
            return self.sprint

        async def get_project(self, project_id):
            return self.project

        async def get_environment(self, environment_id):
            return self.environment

        async def list_environment_vars(self, environment_id):
            return [SimpleNamespace(var_key="token", value="abc")]

        async def list_cases(self, collection_id):
            return self.cases

        def add_all(self, rows):
            self.rows.extend(rows)

        def add(self, row):
            self.rows.append(row)

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    repository = FakeApiCollectionRunRepository()
    service = ApiCollectionRunService(repository)

    payload = await service.run(
        "user-1",
        "collection-1",
        RunApiCaseRequest(environmentId="env-1"),
    )
    assert payload["status"] == "pending"
    assert payload["runtimeVarsJson"] == "{}"


@pytest.mark.asyncio
async def test_api_collection_run_report_includes_case_run_details():
    run = SimpleNamespace(
        collection_run_id="collection-run-1",
        collection_id="collection-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        environment_id="env-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        total_count=1,
        success_count=1,
        failed_count=0,
        error_count=0,
        skipped_count=0,
        runtime_vars_json={"token": "abc"},
        error_message="",
        started_at=None,
        finished_at=None,
        duration_ms=1000,
        created_at=None,
        updated_at=None,
    )
    item = SimpleNamespace(
        item_id="item-1",
        case_id="case-1",
        case_run_id="case-run-1",
        order_no=1,
        status="success",
        continue_on_failure=False,
        error_message="",
        started_at=None,
        finished_at=None,
        duration_ms=1000,
    )
    case = SimpleNamespace(case_id="case-1", name="Ping")
    case_run = SimpleNamespace(
        run_id="case-run-1",
        request_snapshot_json={"method": "GET", "url": "https://api.example.test/ping"},
        response_snapshot_json={"statusCode": 200, "body": "ok"},
        runtime_vars_json={"token": "abc"},
        extract_results_json=[{"success": True}],
        assert_results_json=[{"success": True}],
    )

    class FakeApiCollectionRunRepository:
        session = AuthorizationDatabase()

        async def get_run(self, collection_run_id):
            return run

        async def get_run_scope(self, run):
            return {
                "requirement_id": "requirement-1",
                "sprint_id": "sprint-1",
                "project_id": "project-1",
            }

        async def get_project(self, project_id):
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def list_items(self, collection_run_id):
            return [item]

        async def get_case(self, case_id):
            return case

        async def get_case_run(self, run_id):
            return case_run

    service = ApiCollectionRunService(FakeApiCollectionRunRepository())

    report = await service.report("user-1", "collection-run-1")

    assert report["items"] == [
        {
            "itemId": "item-1",
            "caseId": "case-1",
            "caseRunId": "case-run-1",
            "caseName": "Ping",
            "orderNo": 1,
            "status": "success",
            "continueOnFailure": False,
            "errorMessage": "",
            "startedAt": "",
            "finishedAt": "",
            "durationMs": 1000,
            "request": {"method": "GET", "url": "https://api.example.test/ping"},
            "response": {"statusCode": 200, "body": "ok"},
            "runtimeVarsJson": '{"token":"abc"}',
            "extractResults": [{"success": True}],
            "assertResults": [{"success": True}],
        }
    ]


@pytest.mark.asyncio
async def test_api_worker_snapshot_returns_go_case_run_request_payload():
    task = SimpleNamespace(
        task_id="task-1",
        task_type="api_case_debug",
        domain="api",
        run_id="run-1",
        suite_id="",
        case_id="case-1",
        collection_run_id="",
        collection_id="collection-1",
        generate_task_id="",
        status="claimed",
    )
    run = SimpleNamespace(
        run_id="run-1",
        collection_run_id=None,
        collection_id="collection-1",
        case_id="case-1",
        environment_id="env-1",
        request_snapshot_json={
            "method": "GET",
            "url": "https://api.example.test/ping",
            "headersJson": "{}",
            "queryJson": "{}",
            "bodyType": "none",
            "body": "",
        },
        runtime_vars_json={"token": "abc"},
    )

    class EmptyScalars:
        def all(self):
            return []

    class FakeSession:
        async def scalar(self, statement):
            return run

        async def scalars(self, statement):
            return EmptyScalars()

    payload = await worker.build_snapshot(FakeSession(), "api", task)

    assert payload == {
        "taskType": "api_case_debug",
        "caseRun": {
            "taskId": "task-1",
            "runId": "run-1",
            "collectionId": "collection-1",
            "caseId": "case-1",
            "environmentId": "env-1",
            "request": {
                "method": "GET",
                "url": "https://api.example.test/ping",
                "headersJson": "{}",
                "queryJson": "{}",
                "bodyType": "none",
                "body": "",
            },
            "runtimeVarsJson": '{"token":"abc"}',
            "extractRules": [],
            "assertRules": [],
        },
    }
