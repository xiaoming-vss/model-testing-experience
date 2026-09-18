from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from testing_agent.api.deps import get_current_user_id, get_ui_test_case_service
from testing_agent.app import create_app
from testing_agent.core.errors import ErrUiTestSuiteImportInvalid
from testing_agent.schemas.ui_test_case import UiCaseRequest, UiCaseResponse, UiCaseUpdateRequest
from testing_agent.services.ui_test_case import UiTestCaseService, validate_ui_import_payload


class FakeUpload:
    def __init__(self, content: str):
        self.content = content.encode("utf-8")
        self.filename = "ui-cases.yaml"

    async def read(self) -> bytes:
        return self.content


class UiImportRepository:
    session = AuthorizationDatabase()

    def __init__(self):
        self.rows = []
        self.commits = 0

    async def get_suite(self, suite_id):
        return SimpleNamespace(suite_id=suite_id, requirement_id="requirement-1")

    async def get_requirement(self, requirement_id):
        return SimpleNamespace(requirement_id=requirement_id, sprint_id="sprint-1")

    async def get_sprint(self, sprint_id):
        return SimpleNamespace(sprint_id=sprint_id, project_id="project-1")

    async def get_project(self, project_id):
        return SimpleNamespace(project_id=project_id, user_id="user-1")

    async def get_case(self, case_id):
        return next((row for row in self.rows if row.case_id == case_id), None)

    def add(self, row):
        self.rows.append(row)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _row):
        return None


def import_client(repository):
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ui_test_case_service] = lambda: UiTestCaseService(repository)
    return TestClient(app)


def step(order_no, keyword, **overrides):
    value = {
        "orderNo": order_no,
        "stepName": f"step-{order_no}",
        "keyword": keyword,
        "continueOnFailure": False,
        "enabled": True,
    }
    value.update(overrides)
    return value


def ui_case(*steps, order_no=1, name="登录成功"):
    return {
        "name": name,
        "enabled": True,
        "stepsJson": list(steps),
        "orderNo": order_no,
    }


@pytest.mark.asyncio
async def test_create_normalizes_frontend_steps_json_string_to_array():
    repository = UiImportRepository()
    service = UiTestCaseService(repository)
    steps_json = (
        '[{"orderNo":1,"stepName":"登录","keyword":"open",'
        '"operationValue":"http://www.baidu.com","continueOnFailure":false,"enabled":true}]'
    )

    await service.create(
        "user-1",
        "suite-1",
        UiCaseRequest(
            name="登录成功",
            enabled=True,
            orderNo=1,
            stepsJson=steps_json,
        ),
    )

    assert repository.rows[0].steps_json == [
        {
            "orderNo": 1,
            "stepName": "登录",
            "keyword": "open",
            "operationValue": "http://www.baidu.com",
            "continueOnFailure": False,
            "enabled": True,
        }
    ]


def test_create_endpoint_normalizes_frontend_steps_json_string_to_array():
    repository = UiImportRepository()
    client = import_client(repository)
    steps_json = (
        '[{"orderNo":1,"stepName":"登录","keyword":"open",'
        '"operationValue":"http://www.baidu.com","continueOnFailure":false,"enabled":true}]'
    )

    response = client.post(
        "/v1/ui-test-suites/suite-1/cases",
        json={
            "name": "登录成功",
            "enabled": True,
            "stepsJson": steps_json,
            "orderNo": 1,
        },
    )

    assert response.status_code == 200
    assert isinstance(response.json()["data"]["stepsJson"], list)
    assert isinstance(repository.rows[0].steps_json, list)


@pytest.mark.asyncio
async def test_update_normalizes_frontend_steps_json_string_to_array():
    repository = UiImportRepository()
    service = UiTestCaseService(repository)
    await service.create(
        "user-1",
        "suite-1",
        UiCaseRequest(name="登录成功", enabled=True, orderNo=1, stepsJson=[]),
    )
    case = repository.rows[0]
    body = UiCaseUpdateRequest(stepsJson='[{"orderNo":1,"stepName":"刷新","keyword":"reload"}]')

    await service.update(
        "user-1",
        case.case_id,
        body.model_dump(by_alias=True, exclude_none=True),
    )

    assert case.steps_json == [{"orderNo": 1, "stepName": "刷新", "keyword": "reload"}]


def test_response_normalizes_legacy_steps_json_string_to_array():
    legacy = SimpleNamespace(
        case_id="case-1",
        suite_id="suite-1",
        name="登录成功",
        enabled=True,
        order_no=1,
        steps_json='[{"orderNo":1,"stepName":"登录","keyword":"open"}]',
        created_at=None,
        updated_at=None,
    )

    response = UiCaseResponse.model_validate(legacy).model_dump(by_alias=True, mode="json")

    assert response["stepsJson"] == [{"orderNo": 1, "stepName": "登录", "keyword": "open"}]


@pytest.mark.asyncio
async def test_direct_import_accepts_root_mapping_and_applies_step_defaults():
    repository = UiImportRepository()
    service = UiTestCaseService(repository)
    payload = """name: 登录成功
enabled: true
stepsJson:
  - orderNo: 1
    stepName: 打开登录页
    keyword: open
    operationValue: http://localhost:5173/login
orderNo: 1
"""

    result = await service.import_cases("user-1", "suite-1", payload, None)

    assert result == {"imported": 1}
    assert repository.commits == 1
    assert repository.rows[0].name == "登录成功"
    assert repository.rows[0].steps_json[0]["continueOnFailure"] is False
    assert repository.rows[0].steps_json[0]["enabled"] is True


def test_direct_import_endpoint_accepts_root_mapping_yaml_file():
    repository = UiImportRepository()
    client = import_client(repository)
    payload = """name: 登录成功
enabled: true
stepsJson:
  - orderNo: 1
    stepName: 打开登录页
    keyword: open
    operationValue: http://localhost:5173/login
    continueOnFailure: false
    enabled: true
orderNo: 1
"""

    response = client.post(
        "/v1/ui-test-suites/suite-1/import",
        files={"file": ("ui-cases.yaml", payload.encode("utf-8"), "application/yaml")},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"imported": 1}
    assert repository.rows[0].steps_json[0]["keyword"] == "open"


@pytest.mark.asyncio
async def test_direct_import_accepts_root_list_and_restarts_step_order_per_case():
    repository = UiImportRepository()
    service = UiTestCaseService(repository)
    payload = """- name: 登录成功
  enabled: true
  stepsJson:
    - orderNo: 1
      stepName: 打开登录页
      keyword: open
      operationValue: http://localhost:5173/login
      continueOnFailure: false
      enabled: true
  orderNo: 1
- name: 用户名为空登录失败
  enabled: true
  stepsJson:
    - orderNo: 1
      stepName: 输入密码
      keyword: input
      locatorType: placeholder
      locatorValue: 请输入密码
      operationValue: Pass123456
      continueOnFailure: false
      enabled: true
  orderNo: 2
"""

    result = await service.import_cases("user-1", "suite-1", None, FakeUpload(payload))

    assert result == {"imported": 2}
    assert [row.order_no for row in repository.rows] == [1, 2]
    assert [row.steps_json[0]["orderNo"] for row in repository.rows] == [1, 1]


def test_all_supported_keywords_and_locator_types_are_accepted():
    steps = [
        step(1, "open", operationValue="http://localhost:5173/login"),
        step(2, "reload"),
        step(3, "click", locatorType="css", locatorValue="#submit"),
        step(4, "dblclick", locatorType="xpath", locatorValue="//button"),
        step(
            5,
            "input",
            locatorType="placeholder",
            locatorValue="请输入用户名",
            operationValue="alice",
        ),
        step(6, "clear", locatorType="label", locatorValue="用户名"),
        step(7, "press", locatorType="test_id", locatorValue="name", operationValue="Enter"),
        step(
            8,
            "wait_text",
            locatorType="testid",
            locatorValue="message",
            operationValue="成功",
        ),
        step(
            9,
            "assert_text",
            locatorType="text",
            locatorValue="欢迎",
            operationValue="欢迎",
            comparator="contains",
        ),
        step(
            10,
            "assert_visible",
            locatorType="role",
            locatorValue="button",
            operationValue="5000",
        ),
        step(11, "assert_url", operationValue="/projects", comparator="eq"),
        step(12, "screenshot"),
        step(13, "sleep", operationValue=1000),
    ]

    result = validate_ui_import_payload(ui_case(*steps))

    assert [item["keyword"] for item in result[0]["stepsJson"]] == [
        "open",
        "reload",
        "click",
        "dblclick",
        "input",
        "clear",
        "press",
        "wait_text",
        "assert_text",
        "assert_visible",
        "assert_url",
        "screenshot",
        "sleep",
    ]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "最外层必须是"),
        ({"items": []}, "用例不能为空"),
        (ui_case(order_no=2), "orderNo 必须为 1"),
        (
            ui_case(step(2, "open", operationValue="https://example.test")),
            "stepsJson[0].orderNo 必须为 1",
        ),
        (ui_case(step(1, "wait_visible")), "keyword 仅支持"),
        (ui_case(step(1, "wait_hidden")), "keyword 仅支持"),
        (
            ui_case(step(1, "click", locatorType="id", locatorValue="submit")),
            "locatorType 仅支持",
        ),
        (ui_case(step(1, "click")), "locatorType 不能为空"),
        (
            ui_case(step(1, "open", operationValue="https://example.test", locatorType="css")),
            "不支持 locatorType/locatorValue",
        ),
        (
            ui_case(step(1, "input", locatorType="css", locatorValue="#name")),
            "operationValue 不能为空",
        ),
        (
            ui_case(
                step(
                    1,
                    "input",
                    locatorType="css",
                    locatorValue="#name",
                    operationValue=123,
                )
            ),
            "operationValue 不能为空",
        ),
        (
            ui_case(
                step(
                    1,
                    "assert_text",
                    locatorType="text",
                    locatorValue="成功",
                    operationValue="成功",
                )
            ),
            "comparator 不能为空",
        ),
        (
            ui_case(step(1, "assert_url", operationValue="/home", comparator="regex")),
            "comparator 仅支持",
        ),
        (ui_case(step(1, "sleep", operationValue="later")), "必须是非负毫秒数"),
        (ui_case(step(1, "screenshot", operationValue="x")), "不支持 operationValue"),
        (
            {**ui_case(), "enabled": "true"},
            "enabled 必须是布尔值",
        ),
        (
            {**ui_case(), "description": "unsupported"},
            "description 字段不支持",
        ),
    ],
)
def test_invalid_ui_import_payload_is_rejected(payload, message):
    with pytest.raises(type(ErrUiTestSuiteImportInvalid)) as exc:
        validate_ui_import_payload(payload)

    assert message in str(exc.value)


@pytest.mark.asyncio
async def test_invalid_batch_is_atomic():
    repository = UiImportRepository()
    service = UiTestCaseService(repository)
    payload = {
        "items": [
            ui_case(order_no=1),
            ui_case(step(1, "wait_visible"), order_no=2, name="invalid"),
        ]
    }

    with pytest.raises(type(ErrUiTestSuiteImportInvalid)):
        await service.import_cases("user-1", "suite-1", payload, None)

    assert repository.rows == []
    assert repository.commits == 0
