from __future__ import annotations

from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase

from testing_agent.core.errors import ErrResourceBindingNotFound
from testing_agent.services.function_test_case import FunctionTestCaseService


class FakeFunctionCaseRepository:
    session = AuthorizationDatabase()

    def __init__(
        self,
        *,
        include_requirement_binding: bool = True,
        legacy_remote_types: bool = False,
    ):
        self.suite = SimpleNamespace(suite_id="suite-1", requirement_id="req-1")
        self.requirement = SimpleNamespace(requirement_id="req-1", sprint_id="sprint-1")
        self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
        self.project = SimpleNamespace(project_id="project-1", user_id="user-1")
        self.cases = {
            "case-1": SimpleNamespace(
                case_id="case-1",
                suite_id="suite-1",
                title="登录成功",
                preconditions="账号已注册",
                steps="1. 输入账号\n2. 点击登录",
                expected_results="1. 进入首页\n2. 显示欢迎语",
                priority="P1",
            ),
            "case-2": SimpleNamespace(
                case_id="case-2",
                suite_id="suite-1",
                title="登录失败",
                preconditions="账号不存在",
                steps="1. 输入账号",
                expected_results="1. 提示失败",
                priority="",
            ),
        }
        self.bindings = {
            ("project", "project-1"): SimpleNamespace(
                provider="zentao",
                instance_key="zentao-local",
                instance_url="http://zentao.local",
                connection_id="conn-1",
                remote_resource_type="project",
                remote_resource_id="11",
                remote_parent_id="",
            ),
            ("sprint", "sprint-1"): SimpleNamespace(
                provider="zentao",
                instance_key="zentao-local",
                instance_url="http://zentao.local",
                connection_id="conn-1",
                remote_resource_type="sprint" if legacy_remote_types else "execution",
                remote_resource_id="22",
                remote_parent_id="11",
            ),
        }
        if include_requirement_binding:
            self.bindings[("requirement", "req-1")] = SimpleNamespace(
                provider="zentao",
                instance_key="zentao-local",
                instance_url="http://zentao.local",
                connection_id="conn-1",
                remote_resource_type="requirement" if legacy_remote_types else "story",
                remote_resource_id="33",
                remote_parent_id="22",
            )

    async def get_suite(self, suite_id):
        return self.suite if suite_id == self.suite.suite_id else None

    async def get_requirement(self, requirement_id):
        return self.requirement if requirement_id == self.requirement.requirement_id else None

    async def get_sprint(self, sprint_id):
        return self.sprint if sprint_id == self.sprint.sprint_id else None

    async def get_project(self, project_id):
        return self.project if project_id == self.project.project_id else None

    async def list_by_suite(self, suite_id):
        return [case for case in self.cases.values() if case.suite_id == suite_id]

    async def get_case(self, case_id):
        return self.cases.get(case_id)

    async def get_active_binding(self, resource_type, resource_id):
        return self.bindings.get((resource_type, resource_id))


class FakeIntegrationConnectionService:
    def __init__(self):
        self.calls = []

    async def resolve_personal_connection(
        self, user_id, provider, project_id, instance_url, connection_id=""
    ):
        assert provider == "zentao"
        assert user_id == "user-1"
        return SimpleNamespace(connection_id=connection_id or "conn-1")

    async def resolve_zentao_access(self, user_id, connection_id, project_id=""):
        self.calls.append((user_id, connection_id, project_id))
        return SimpleNamespace(
            connection_id=connection_id,
            base_url="http://zentao.local",
            access_token="token-1",
        )


class FakeZentaoResourceClient:
    def __init__(self):
        self.calls = []

    async def create_test_cases(self, connection, body):
        self.calls.append((connection, body))
        return {
            "total": len(body["cases"]),
            "items": [
                {"id": 101 + index, "status": "success"} for index, _ in enumerate(body["cases"])
            ],
        }


@pytest.mark.asyncio
async def test_function_case_import_to_zentao_imports_all_cases():
    repository = FakeFunctionCaseRepository()
    integration_service = FakeIntegrationConnectionService()
    zentao_client = FakeZentaoResourceClient()
    service = FunctionTestCaseService(repository, integration_service, zentao_client)

    result = await service.import_to_zentao(
        "user-1",
        "suite-1",
        {"productId": 9, "moduleId": 8},
    )

    assert result["suiteId"] == "suite-1"
    assert result["productId"] == 9
    assert result["remoteProjectId"] == 11
    assert result["remoteExecutionId"] == 22
    assert result["importedCaseCount"] == 2
    assert result["items"][0] == {
        "caseId": "case-1",
        "remoteCaseId": 101,
        "status": "success",
    }
    assert integration_service.calls == [("user-1", "conn-1", "project-1")]

    _, body = zentao_client.calls[0]
    assert body["productID"] == 9
    assert body["project"] == 11
    assert body["execution"] == 22
    assert body["cases"][0] == {
        "title": "登录成功",
        "module": 8,
        "story": 33,
        "pri": 1,
        "precondition": "账号已注册",
        "steps": ["1. 输入账号", "2. 点击登录"],
        "expects": ["1. 进入首页", "2. 显示欢迎语"],
    }
    assert body["cases"][1]["pri"] == 3


@pytest.mark.asyncio
async def test_function_case_import_to_zentao_imports_selected_cases():
    zentao_client = FakeZentaoResourceClient()
    service = FunctionTestCaseService(
        FakeFunctionCaseRepository(),
        FakeIntegrationConnectionService(),
        zentao_client,
    )

    result = await service.import_to_zentao(
        "user-1",
        "suite-1",
        {"productId": 9, "caseIds": ["case-2"]},
    )

    assert result["importedCaseCount"] == 1
    assert result["items"][0]["caseId"] == "case-2"
    assert zentao_client.calls[0][1]["cases"][0]["title"] == "登录失败"
    assert zentao_client.calls[0][1]["cases"][0]["module"] == 0


@pytest.mark.asyncio
async def test_function_case_import_to_zentao_accepts_legacy_binding_type_labels():
    service = FunctionTestCaseService(
        FakeFunctionCaseRepository(legacy_remote_types=True),
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(),
    )

    result = await service.import_to_zentao("user-1", "suite-1", {"productId": 9})

    assert result["remoteProjectId"] == 11
    assert result["remoteExecutionId"] == 22
    assert result["importedCaseCount"] == 2


@pytest.mark.asyncio
async def test_function_case_import_to_zentao_rejects_missing_requirement_binding():
    service = FunctionTestCaseService(
        FakeFunctionCaseRepository(include_requirement_binding=False),
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(),
    )

    with pytest.raises(type(ErrResourceBindingNotFound)) as exc_info:
        await service.import_to_zentao("user-1", "suite-1", {"productId": 9})

    assert exc_info.value.code == ErrResourceBindingNotFound.code
    assert exc_info.value.message == "请先绑定所属需求"


@pytest.mark.asyncio
async def test_function_case_list_returns_total_and_items():
    service = FunctionTestCaseService(FakeFunctionCaseRepository())

    result = await service.list("user-1", "suite-1")

    assert result["total"] == 2
    assert [item["caseId"] for item in result["items"]] == ["case-1", "case-2"]
    assert result["items"][0]["suiteId"] == "suite-1"
    assert result["items"][0]["expectedResults"] == "1. 进入首页\n2. 显示欢迎语"
