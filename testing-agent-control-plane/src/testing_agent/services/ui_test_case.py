from __future__ import annotations

from typing import Any

from testing_agent.core.errors import (
    ErrNotFound,
    ErrUiTestSuiteImportInvalid,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.repositories.ui_test_case import UiTestCaseRepository
from testing_agent.schemas.ui_test_case import UiCaseRequest, UiCaseResponse
from testing_agent.services.api_collection import read_import_payload
from testing_agent.services.common import apply_patch, dump, list_payload
from testing_agent.services.project_access import ProjectAction, require_project_access

UI_IMPORT_CASE_FIELDS = {"name", "enabled", "stepsJson", "orderNo"}
UI_IMPORT_STEP_FIELDS = {
    "orderNo",
    "stepName",
    "keyword",
    "locatorType",
    "locatorValue",
    "operationValue",
    "comparator",
    "continueOnFailure",
    "enabled",
}
UI_IMPORT_LOCATOR_TYPES = {
    "css",
    "xpath",
    "text",
    "placeholder",
    "label",
    "test_id",
    "testid",
    "role",
}
UI_IMPORT_KEYWORDS = {
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
}
UI_IMPORT_COMPARATORS = {"eq", "contains"}
UI_KEYWORDS_REQUIRING_LOCATOR = {
    "click",
    "dblclick",
    "input",
    "clear",
    "press",
    "wait_text",
    "assert_text",
    "assert_visible",
}
UI_KEYWORDS_WITHOUT_LOCATOR = UI_IMPORT_KEYWORDS - UI_KEYWORDS_REQUIRING_LOCATOR
UI_KEYWORDS_REQUIRING_OPERATION = {
    "open",
    "input",
    "press",
    "wait_text",
    "assert_text",
    "assert_visible",
    "assert_url",
    "sleep",
}
UI_KEYWORDS_WITHOUT_OPERATION = {"clear", "screenshot"}
UI_KEYWORDS_REQUIRING_COMPARATOR = {"assert_text", "assert_url"}


def ui_import_error(message: str):
    return dynamic_error(ErrUiTestSuiteImportInvalid, message)


def require_non_empty_string(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ui_import_error(f"{field_path} 不能为空")
    return value


def require_positive_order(value: Any, field_path: str, expected: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ui_import_error(f"{field_path} 必须是整数")
    if value != expected:
        raise ui_import_error(f"{field_path} 必须为 {expected}")
    return value


def require_boolean(value: Any, field_path: str) -> bool:
    if not isinstance(value, bool):
        raise ui_import_error(f"{field_path} 必须是布尔值")
    return value


def check_ui_import_fields(item: dict[str, Any], allowed: set[str], field_path: str) -> None:
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise ui_import_error(f"{field_path}.{unknown[0]} 字段不支持")


def has_operation_value(step: dict[str, Any]) -> bool:
    value = step.get("operationValue")
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def require_milliseconds(value: Any, field_path: str) -> None:
    if isinstance(value, bool):
        raise ui_import_error(f"{field_path} 必须是非负毫秒数")
    if isinstance(value, int):
        valid = value >= 0
    elif isinstance(value, str):
        valid = value.strip().isdigit()
    else:
        valid = False
    if not valid:
        raise ui_import_error(f"{field_path} 必须是非负毫秒数")


def validate_ui_import_step(step: Any, case_index: int, step_index: int) -> dict[str, Any]:
    field_path = f"cases[{case_index}].stepsJson[{step_index}]"
    if not isinstance(step, dict):
        raise ui_import_error(f"{field_path} 必须是对象")
    check_ui_import_fields(step, UI_IMPORT_STEP_FIELDS, field_path)
    normalized = dict(step)

    require_positive_order(step.get("orderNo"), f"{field_path}.orderNo", step_index + 1)
    require_non_empty_string(step.get("stepName"), f"{field_path}.stepName")
    keyword = require_non_empty_string(step.get("keyword"), f"{field_path}.keyword").strip()
    if keyword not in UI_IMPORT_KEYWORDS:
        allowed = " | ".join(sorted(UI_IMPORT_KEYWORDS))
        raise ui_import_error(f"{field_path}.keyword 仅支持 {allowed}")

    normalized["continueOnFailure"] = require_boolean(
        step.get("continueOnFailure", False), f"{field_path}.continueOnFailure"
    )
    normalized["enabled"] = require_boolean(step.get("enabled", True), f"{field_path}.enabled")

    locator_type = step.get("locatorType")
    locator_value = step.get("locatorValue")
    if keyword in UI_KEYWORDS_REQUIRING_LOCATOR:
        locator_type = require_non_empty_string(locator_type, f"{field_path}.locatorType").strip()
        if locator_type not in UI_IMPORT_LOCATOR_TYPES:
            allowed = " | ".join(sorted(UI_IMPORT_LOCATOR_TYPES))
            raise ui_import_error(f"{field_path}.locatorType 仅支持 {allowed}")
        require_non_empty_string(locator_value, f"{field_path}.locatorValue")
    elif keyword in UI_KEYWORDS_WITHOUT_LOCATOR and (
        locator_type is not None or locator_value is not None
    ):
        raise ui_import_error(f"{field_path}.{keyword} 不支持 locatorType/locatorValue")

    if keyword in UI_KEYWORDS_REQUIRING_OPERATION:
        if not has_operation_value(step):
            raise ui_import_error(f"{field_path}.operationValue 不能为空")
        if keyword not in {"assert_visible", "sleep"}:
            require_non_empty_string(step.get("operationValue"), f"{field_path}.operationValue")
    if keyword in UI_KEYWORDS_WITHOUT_OPERATION and "operationValue" in step:
        raise ui_import_error(f"{field_path}.{keyword} 不支持 operationValue")
    if keyword in {"assert_visible", "sleep"}:
        require_milliseconds(step.get("operationValue"), f"{field_path}.operationValue")

    comparator = step.get("comparator")
    if keyword in UI_KEYWORDS_REQUIRING_COMPARATOR:
        comparator = require_non_empty_string(comparator, f"{field_path}.comparator").strip()
        if comparator not in UI_IMPORT_COMPARATORS:
            allowed = " | ".join(sorted(UI_IMPORT_COMPARATORS))
            raise ui_import_error(f"{field_path}.comparator 仅支持 {allowed}")
    elif comparator is not None:
        raise ui_import_error(f"{field_path}.{keyword} 不支持 comparator")
    return normalized


def ui_import_cases(payload: dict[str, Any]) -> list[Any]:
    # read_import_payload preserves mappings and wraps a root YAML list as {"items": [...]}.
    if isinstance(payload.get("items"), list) and len(payload) == 1:
        return payload["items"]
    if set(payload) & UI_IMPORT_CASE_FIELDS:
        return [payload]
    # Keep the two legacy wrappers accepted before the formal mapping/list contract.
    for key in ("cases", "uiCases"):
        if isinstance(payload.get(key), list) and len(payload) == 1:
            return payload[key]
    raise ui_import_error("最外层必须是单条用例对象或多条用例数组")


def validate_ui_import_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    cases = ui_import_cases(payload)
    if not cases:
        raise ui_import_error("用例不能为空")
    normalized_cases: list[dict[str, Any]] = []
    for case_index, case in enumerate(cases):
        field_path = f"cases[{case_index}]"
        if not isinstance(case, dict):
            raise ui_import_error(f"{field_path} 必须是对象")
        check_ui_import_fields(case, UI_IMPORT_CASE_FIELDS, field_path)
        name = require_non_empty_string(case.get("name"), f"{field_path}.name")
        enabled = require_boolean(case.get("enabled"), f"{field_path}.enabled")
        order_no = require_positive_order(
            case.get("orderNo"), f"{field_path}.orderNo", case_index + 1
        )
        steps = case.get("stepsJson")
        if not isinstance(steps, list):
            raise ui_import_error(f"{field_path}.stepsJson 必须是数组")
        normalized_cases.append(
            {
                "name": name,
                "enabled": enabled,
                "orderNo": order_no,
                "stepsJson": [
                    validate_ui_import_step(step, case_index, step_index)
                    for step_index, step in enumerate(steps)
                ],
            }
        )
    return normalized_cases


class UiTestCaseService:
    def __init__(self, repository: UiTestCaseRepository):
        self.repository = repository

    async def get_accessible_suite(
        self, user_id: str, suite_id: str, *, action: ProjectAction = "read"
    ) -> UiTestSuite:
        suite = await self.repository.get_suite(suite_id)
        if suite is None:
            raise ErrNotFound
        requirement = await self.repository.get_requirement(suite.requirement_id)
        if requirement is None:
            raise ErrNotFound
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)
        return suite

    async def get_accessible_entity(
        self, user_id: str, case_id: str, *, action: ProjectAction = "read"
    ) -> UiTestCase:
        case = await self.repository.get_case(case_id)
        if case is None:
            raise ErrNotFound
        await self.get_accessible_suite(user_id, case.suite_id, action=action)
        return case

    async def create(self, user_id: str, suite_id: str, body: UiCaseRequest) -> dict:
        await self.get_accessible_suite(user_id, suite_id, action="write")
        case = UiTestCase(
            case_id=new_id(),
            suite_id=suite_id,
            **body.model_dump(by_alias=False),
        )
        self.repository.add(case)
        await self.repository.commit()
        await self.repository.refresh(case)
        return dump(UiCaseResponse, case)

    async def import_cases(self, user_id: str, suite_id: str, payload: Any, file: Any) -> dict:
        await self.get_accessible_suite(user_id, suite_id, action="write")
        parsed = await read_import_payload(payload, file)
        cases = validate_ui_import_payload(parsed)
        for item in cases:
            self.repository.add(
                UiTestCase(
                    case_id=new_id(),
                    suite_id=suite_id,
                    name=item["name"],
                    enabled=item["enabled"],
                    order_no=item["orderNo"],
                    steps_json=item["stepsJson"],
                )
            )
        await self.repository.commit()
        return {"imported": len(cases)}

    async def list(self, user_id: str, suite_id: str) -> dict[str, Any]:
        await self.get_accessible_suite(user_id, suite_id, action="read")
        rows = await self.repository.list_by_suite(suite_id)
        return list_payload([dump(UiCaseResponse, row) for row in rows])

    async def get(self, user_id: str, case_id: str) -> dict:
        return dump(
            UiCaseResponse, await self.get_accessible_entity(user_id, case_id, action="read")
        )

    async def update(self, user_id: str, case_id: str, body: dict[str, Any]) -> dict:
        case = await self.get_accessible_entity(user_id, case_id, action="write")
        apply_patch(case, body, {"name", "enabled", "order_no", "steps_json"})
        await self.repository.commit()
        await self.repository.refresh(case)
        return dump(UiCaseResponse, case)

    async def delete(self, user_id: str, case_id: str) -> dict:
        case = await self.get_accessible_entity(user_id, case_id, action="write")
        await self.repository.hard_delete(case)
        await self.repository.commit()
        return {}
