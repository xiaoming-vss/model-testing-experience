from fastapi.testclient import TestClient

from app.dependencies import (
    get_zentao_bug_service_factory,
    get_zentao_execution_service_factory,
    get_zentao_project_service_factory,
    get_zentao_testcase_service_factory,
    get_zentao_testtask_service_factory,
)
from app.main import create_app
from app.schemas.zentao.bug import BugImportData
from app.schemas.zentao.imports import (
    ExecutionImportData,
    ImportListData,
    ImportListQuery,
    ProjectImportData,
    StoryImportData,
)
from app.schemas.zentao.imports import TestTaskImportData as TaskImportData
from app.schemas.zentao.testcase import (
    TestCaseBatchCreateData as BatchCreateCaseData,
)
from app.schemas.zentao.testcase import (
    TestCaseBatchCreateRequest as BatchCreateCaseRequest,
)
from app.schemas.zentao.testcase import (
    TestCaseCreateData as CreateCaseData,
)
from app.schemas.zentao.testcase import (
    TestCaseImportData as CaseImportData,
)


class FakeZentaoServices:
    async def list_projects(self, query: ImportListQuery) -> ImportListData[ProjectImportData]:
        assert query.page == 1
        assert query.page_size == 100
        return ImportListData(
            total=1,
            items=[
                ProjectImportData(
                    id=1,
                    name="Demo Project",
                    code="DEMO",
                    description="Project desc",
                    status="doing",
                    begin="2026-01-01T00:00:00+08:00",
                    end="2026-03-31T00:00:00+08:00",
                    created_at=None,
                    updated_at=None,
                    deleted=False,
                )
            ],
        )

    async def get_project(self, project_id: int) -> ProjectImportData:
        assert project_id == 1
        return ProjectImportData(
            id=1,
            name="Demo Project",
            code="DEMO",
            description="Project desc",
            status="doing",
            begin="2026-01-01T00:00:00+08:00",
            end="2026-03-31T00:00:00+08:00",
            deleted=False,
        )

    async def list_executions(
        self,
        project_id: int,
        query: ImportListQuery,
    ) -> ImportListData[ExecutionImportData]:
        assert project_id == 2
        assert query.page == 1
        assert query.page_size == 100
        return ImportListData(
            total=1,
            items=[
                ExecutionImportData(
                    id=11,
                    project_id=project_id,
                    name="Sprint 1",
                    description="Execution desc",
                    status="wait",
                    begin="2026-01-02T00:00:00+08:00",
                    end="2026-01-20T00:00:00+08:00",
                    parent_id=None,
                    created_at=None,
                    updated_at=None,
                    deleted=False,
                )
            ],
        )

    async def get_execution(self, execution_id: int) -> ExecutionImportData:
        assert execution_id == 11
        return ExecutionImportData(
            id=11,
            project_id=2,
            name="Sprint 1",
            description="Execution desc",
            status="wait",
            begin="2026-01-02T00:00:00+08:00",
            end="2026-01-20T00:00:00+08:00",
            parent_id=None,
            deleted=False,
        )

    async def list_execution_stories(
        self,
        execution_id: int,
    ) -> ImportListData[StoryImportData]:
        assert execution_id == 11
        return ImportListData(
            total=1,
            items=[
                StoryImportData(
                    id=21,
                    title="Support login by phone",
                    product_id=1,
                    module_id=2,
                    plan_id=3,
                    status="active",
                    stage="developing",
                    priority="P2",
                    assigned_to="dev1",
                    opened_by="pm1",
                    created_at="2026-05-01T10:00:00+08:00",
                    deleted=False,
                )
            ],
        )

    async def list_testtasks(
        self,
        execution_id: int,
        query: ImportListQuery,
    ) -> ImportListData[TaskImportData]:
        assert execution_id == 11
        assert query.page == 1
        assert query.page_size == 100
        return ImportListData(
            total=1,
            items=[
                TaskImportData(
                    id=101,
                    project_id=1,
                    execution_id=execution_id,
                    name="Regression Test Task",
                    title=None,
                    description="Test task desc",
                    status="wait",
                    type="system",
                    owner="tester1",
                    opened_by="admin",
                    begin="2026-05-01T00:00:00+08:00",
                    end="2026-05-05T00:00:00+08:00",
                    deleted=False,
                )
            ],
        )

    async def list_execution_bugs(
        self,
        execution_id: int,
        query: ImportListQuery,
    ) -> ImportListData[BugImportData]:
        assert execution_id == 11
        assert query.page == 1
        assert query.page_size == 100
        return ImportListData(
            total=1,
            items=[
                BugImportData(
                    id=201,
                    openedDate="2026-06-01T10:00:00+08:00",
                    resolvedDate="2026-06-02T11:00:00+08:00",
                    status="active",
                    type="code",
                    pri=2,
                    severity=3,
                    title="Crash on login",
                    plan=7,
                    execution=11,
                    module=5,
                    product=1,
                )
            ],
        )

    async def get_testtask(self, testtask_id: int) -> TaskImportData:
        assert testtask_id == 101
        return TaskImportData(
            id=101,
            project_id=1,
            execution_id=11,
            name="Regression Test Task",
            title=None,
            description="Test task desc",
            status="wait",
            type="system",
            owner="tester1",
            opened_by="admin",
            begin="2026-05-01T00:00:00+08:00",
            end="2026-05-05T00:00:00+08:00",
            deleted=False,
        )

    async def list_execution_cases(
        self,
        execution_id: int,
        query: ImportListQuery,
    ) -> ImportListData[CaseImportData]:
        assert execution_id == 11
        assert query.page == 1
        assert query.page_size == 100
        return ImportListData(
            total=1,
            items=[
                CaseImportData(
                    id="123",
                    module="Login Module",
                    title="Login succeeds",
                    preconditions="User is registered",
                    steps="1. Enter account and password\n2. Click login",
                    expectedResults="1. Input succeeds\n2. Login succeeds",
                    priority="P1",
                    caseType="functional",
                    status="normal",
                    lastRunDate="2026-06-10T09:30:00+08:00",
                    lastRunResult="pass",
                    orderNo=1,
                    deleted=False,
                )
            ],
        )

    async def create_testcases(
        self,
        payload: BatchCreateCaseRequest,
    ) -> BatchCreateCaseData:
        assert payload.productID == 1
        assert payload.project == 2
        assert payload.execution == 3
        assert len(payload.cases) == 2
        assert payload.cases[0].title == "测试压敏模块显示是否正常"
        assert payload.cases[0].module == 0
        assert payload.cases[0].story == 0
        assert payload.cases[0].pri == 3
        assert payload.cases[0].precondition == "已进入压敏模块页面"
        assert payload.cases[0].steps == ["步骤1", "步骤2"]
        assert payload.cases[0].expects == ["期望1", "期望2"]
        assert payload.cases[1].title == "第二条测试用例"
        return BatchCreateCaseData(
            total=2,
            items=[
                CreateCaseData(id=456, status="success"),
                CreateCaseData(id=457, status="success"),
            ],
        )


def build_override_client() -> TestClient:
    app = create_app()
    fake_services = FakeZentaoServices()
    app.dependency_overrides[get_zentao_project_service_factory] = lambda: (
        lambda base_url, token: fake_services
    )
    app.dependency_overrides[get_zentao_execution_service_factory] = lambda: (
        lambda base_url, token: fake_services
    )
    app.dependency_overrides[get_zentao_bug_service_factory] = lambda: (
        lambda base_url, token: fake_services
    )
    app.dependency_overrides[get_zentao_testtask_service_factory] = lambda: (
        lambda base_url, token: fake_services
    )
    app.dependency_overrides[get_zentao_testcase_service_factory] = lambda: (
        lambda base_url, token: fake_services
    )
    return TestClient(app)


def test_get_projects() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/projects?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"][0]["name"] == "Demo Project"
    assert payload["data"]["items"][0]["description"] == "Project desc"


def test_get_project_detail() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/projects/1?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["id"] == 1
    assert payload["data"]["name"] == "Demo Project"


def test_get_project_executions() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/projects/2/executions?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"][0]["name"] == "Sprint 1"
    assert payload["data"]["items"][0]["project_id"] == 2


def test_get_execution_detail() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/executions/11?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["data"]["id"] == 11
    assert payload["data"]["name"] == "Sprint 1"


def test_get_execution_stories() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/executions/11/stories?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"][0]["id"] == 21
    assert payload["data"]["items"][0]["title"] == "Support login by phone"
    assert payload["data"]["items"][0]["priority"] == "P2"


def test_get_execution_testtasks() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/executions/11/testtasks?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"][0]["name"] == "Regression Test Task"


def test_get_execution_bugs() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/executions/11/bugs?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"][0] == {
        "id": 201,
        "openedDate": "2026-06-01T10:00:00+08:00",
        "resolvedDate": "2026-06-02T11:00:00+08:00",
        "status": "active",
        "type": "code",
        "pri": 2,
        "severity": 3,
        "title": "Crash on login",
        "plan": 7,
        "execution": 11,
        "module": 5,
        "product": 1,
    }


def test_get_testtask_detail() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/testtasks/101?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["data"]["id"] == 101
    assert payload["data"]["name"] == "Regression Test Task"


def test_get_execution_cases() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/executions/11/cases?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"][0]["id"] == "123"
    assert payload["data"]["items"][0]["title"] == "Login succeeds"
    assert payload["data"]["items"][0]["expectedResults"] == (
        "1. Input succeeds\n2. Login succeeds"
    )
    assert payload["data"]["items"][0]["status"] == "normal"
    assert payload["data"]["items"][0]["lastRunDate"] == "2026-06-10T09:30:00+08:00"
    assert payload["data"]["items"][0]["lastRunResult"] == "pass"


def test_create_testcases() -> None:
    client = build_override_client()

    response = client.post(
        "/api/v1/zentao/testcases?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
        json={
            "productID": 1,
            "project": 2,
            "execution": 3,
            "cases": [
                {
                    "title": "测试压敏模块显示是否正常",
                    "module": 0,
                    "story": 0,
                    "pri": 3,
                    "precondition": "已进入压敏模块页面",
                    "steps": ["步骤1", "步骤2"],
                    "expects": ["期望1", "期望2"],
                },
                {
                    "title": "第二条测试用例",
                    "module": 0,
                    "story": 0,
                    "pri": 3,
                    "precondition": "",
                    "steps": ["步骤A"],
                    "expects": ["期望A"],
                },
            ],
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"] == {
        "total": 2,
        "items": [
            {"id": 456, "status": "success"},
            {"id": 457, "status": "success"},
        ],
    }


def test_phase_one_rejects_legacy_query_parameters() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/projects?base_url=https://zentao.example.com&browseType=undone",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 400
    assert payload["code"] == 42000
    assert payload["message"] == "Unsupported query parameter(s): browseType"


def test_phase_one_rejects_unknown_query_parameters() -> None:
    client = build_override_client()

    response = client.get(
        "/api/v1/zentao/projects?base_url=https://zentao.example.com&foo=bar",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 400
    assert payload["code"] == 42000
    assert payload["message"] == "Unsupported query parameter(s): foo"


def test_phase_one_requires_bearer_authorization() -> None:
    client = create_app()
    response = TestClient(client).get(
        "/api/v1/zentao/projects?base_url=https://zentao.example.com",
        headers={"Authorization": "demo-token"},
    )

    payload = response.json()
    assert response.status_code == 400
    assert payload["code"] == 42000
    assert payload["message"] == (
        "Missing Zentao token. Provide it with `Authorization: Bearer <token>`."
    )
