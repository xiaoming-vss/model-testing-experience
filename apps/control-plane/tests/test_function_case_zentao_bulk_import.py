from __future__ import annotations

from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from pydantic import ValidationError

from testing_agent.app import create_app
from testing_agent.core.errors import ErrBadRequest, ErrForbidden, ErrNotFound
from testing_agent.schemas.function_test_case import (
    FunctionSuitesZentaoImportResponse,
    ImportFunctionSuitesToZentaoRequest,
)
from testing_agent.services.function_test_case import FunctionTestCaseService


def make_case(case_id: str, suite_id: str, title: str) -> SimpleNamespace:
    return SimpleNamespace(
        case_id=case_id,
        suite_id=suite_id,
        title=title,
        preconditions="前置条件",
        steps="步骤一",
        expected_results="结果一",
        priority="P2",
    )


class BulkImportRepository:
    session = AuthorizationDatabase()

    def __init__(self, *, owner_id: str = "user-1"):
        self.requirement = SimpleNamespace(requirement_id="req-1", sprint_id="sprint-1")
        self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
        self.project = SimpleNamespace(project_id="project-1", user_id=owner_id)
        self.suites = {
            suite_id: SimpleNamespace(suite_id=suite_id, requirement_id="req-1")
            for suite_id in ("suite-1", "suite-2", "suite-3")
        }
        self.suites["other-suite"] = SimpleNamespace(suite_id="other-suite", requirement_id="req-2")
        self.cases = {
            "suite-1": [make_case("case-1", "suite-1", "用例一")],
            "suite-2": [make_case("case-2", "suite-2", "用例二")],
            "suite-3": [make_case("case-3", "suite-3", "用例三")],
            "other-suite": [make_case("case-4", "other-suite", "其他用例")],
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
                remote_resource_type="execution",
                remote_resource_id="22",
                remote_parent_id="11",
            ),
            ("requirement", "req-1"): SimpleNamespace(
                provider="zentao",
                instance_key="zentao-local",
                instance_url="http://zentao.local",
                connection_id="conn-1",
                remote_resource_type="story",
                remote_resource_id="33",
                remote_parent_id="22",
            ),
        }

    async def get_requirement(self, requirement_id):
        return self.requirement if requirement_id == "req-1" else None

    async def get_sprint(self, sprint_id):
        return self.sprint if sprint_id == "sprint-1" else None

    async def get_project(self, project_id):
        return self.project if project_id == "project-1" else None

    async def list_suites_by_ids(self, suite_ids):
        return [self.suites[suite_id] for suite_id in suite_ids if suite_id in self.suites]

    async def list_by_suite(self, suite_id):
        return self.cases.get(suite_id, [])

    async def get_active_binding(self, resource_type, resource_id):
        return self.bindings.get((resource_type, resource_id))


class RecordingConnectionService:
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


class RecordingZentaoClient:
    def __init__(self, *, failed_titles: set[str] | None = None):
        self.failed_titles = failed_titles or set()
        self.calls = []

    async def create_test_cases(self, connection, body):
        self.calls.append((connection, body))
        title = body["cases"][0]["title"]
        if title in self.failed_titles:
            raise RuntimeError(f"导入失败: {title}")
        return {
            "items": [{"id": 100 + len(self.calls), "status": "success"} for _ in body["cases"]]
        }


def build_service(repository=None, client=None):
    connections = RecordingConnectionService()
    zentao = client or RecordingZentaoClient()
    service = FunctionTestCaseService(repository or BulkImportRepository(), connections, zentao)
    return service, connections, zentao


@pytest.mark.asyncio
async def test_bulk_import_imports_selected_suites_and_resolves_connection_once():
    service, connections, zentao = build_service()

    result = await service.import_requirement_to_zentao(
        "user-1",
        "req-1",
        {"productId": 9, "moduleId": 8, "suiteIds": ["suite-1", "suite-2"]},
    )

    assert result == {
        "requirementId": "req-1",
        "status": "success",
        "totalSuiteCount": 2,
        "succeededSuiteCount": 2,
        "failedSuiteCount": 0,
        "importedCaseCount": 2,
        "items": [
            {"suiteId": "suite-1", "status": "success", "importedCaseCount": 1},
            {"suiteId": "suite-2", "status": "success", "importedCaseCount": 1},
        ],
    }
    assert connections.calls == [("user-1", "conn-1", "project-1")]
    assert len(zentao.calls) == 2
    assert all(body["productID"] == 9 for _, body in zentao.calls)
    assert all(body["cases"][0]["module"] == 8 for _, body in zentao.calls)
    assert [body["cases"][0]["title"] for _, body in zentao.calls] == ["用例一", "用例二"]


@pytest.mark.asyncio
async def test_bulk_import_continues_after_suite_failure():
    client = RecordingZentaoClient(failed_titles={"用例二"})
    service, _, zentao = build_service(client=client)

    result = await service.import_requirement_to_zentao(
        "user-1",
        "req-1",
        {
            "productId": 9,
            "suiteIds": ["suite-1", "suite-2", "suite-3"],
        },
    )

    assert result["status"] == "partial_failure"
    assert result["succeededSuiteCount"] == 2
    assert result["failedSuiteCount"] == 1
    assert result["importedCaseCount"] == 2
    assert result["items"][1] == {
        "suiteId": "suite-2",
        "status": "failed",
        "importedCaseCount": 0,
        "errorCode": 3505,
        "errorMessage": "导入失败: 用例二",
    }
    assert len(zentao.calls) == 3


@pytest.mark.asyncio
async def test_bulk_import_reports_failed_when_every_suite_fails():
    client = RecordingZentaoClient(failed_titles={"用例一", "用例二"})
    service, _, _ = build_service(client=client)

    result = await service.import_requirement_to_zentao(
        "user-1",
        "req-1",
        {"productId": 9, "suiteIds": ["suite-1", "suite-2"]},
    )

    assert result["status"] == "failed"
    assert result["succeededSuiteCount"] == 0
    assert result["failedSuiteCount"] == 2
    assert result["importedCaseCount"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"productId": 9, "suiteIds": []}, type(ErrBadRequest)),
        ({"productId": 0, "suiteIds": ["suite-1"]}, type(ErrBadRequest)),
        ({"productId": 9, "moduleId": -1, "suiteIds": ["suite-1"]}, type(ErrBadRequest)),
        (
            {"productId": 9, "suiteIds": ["suite-1", "suite-1"]},
            type(ErrBadRequest),
        ),
        ({"productId": 9, "suiteIds": ["missing-suite"]}, type(ErrNotFound)),
    ],
)
async def test_bulk_import_rejects_invalid_scope_before_calling_zentao(payload, error_type):
    service, connections, zentao = build_service()

    with pytest.raises(error_type):
        await service.import_requirement_to_zentao("user-1", "req-1", payload)

    assert connections.calls == []
    assert zentao.calls == []


@pytest.mark.asyncio
async def test_bulk_import_rejects_suite_from_another_requirement_before_remote_access():
    service, connections, zentao = build_service()

    with pytest.raises(type(ErrBadRequest)) as exc_info:
        await service.import_requirement_to_zentao(
            "user-1",
            "req-1",
            {"productId": 9, "suiteIds": ["suite-1", "other-suite"]},
        )

    assert exc_info.value.code == 3303
    assert exc_info.value.message == "测试集不属于当前需求: other-suite"
    assert connections.calls == []
    assert zentao.calls == []


@pytest.mark.asyncio
async def test_bulk_import_rejects_non_owner_before_remote_access():
    service, connections, zentao = build_service(
        repository=BulkImportRepository(owner_id="other-user")
    )

    with pytest.raises(type(ErrForbidden)):
        await service.import_requirement_to_zentao(
            "user-1",
            "req-1",
            {"productId": 9, "suiteIds": ["suite-1"]},
        )

    assert connections.calls == []
    assert zentao.calls == []


def test_bulk_import_request_rejects_blank_and_duplicate_suite_ids():
    with pytest.raises(ValidationError):
        ImportFunctionSuitesToZentaoRequest(productId=9, suiteIds=["suite-1", " "])
    with pytest.raises(ValidationError):
        ImportFunctionSuitesToZentaoRequest(productId=9, suiteIds=["suite-1", "suite-1"])


def test_bulk_import_response_uses_camel_case_and_omits_success_errors():
    response = FunctionSuitesZentaoImportResponse.model_validate(
        {
            "requirementId": "req-1",
            "status": "success",
            "totalSuiteCount": 1,
            "succeededSuiteCount": 1,
            "failedSuiteCount": 0,
            "importedCaseCount": 2,
            "items": [
                {
                    "suiteId": "suite-1",
                    "status": "success",
                    "importedCaseCount": 2,
                }
            ],
        }
    )

    assert response.model_dump(by_alias=True, exclude_none=True)["items"] == [
        {"suiteId": "suite-1", "status": "success", "importedCaseCount": 2}
    ]


def test_bulk_import_route_is_public():
    paths = create_app().openapi()["paths"]

    assert "post" in paths["/v1/requirements/{requirementId}/zentao/testcases/import"]
