from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from testing_agent.core.errors import AppError
from testing_agent.schemas.ui_run import DebugRunUiCaseRequest, RunUiSuiteRequest
from testing_agent.services.ui_test_case import validate_ui_import_payload
from testing_agent.services.ui_test_case_run import UiTestCaseRunService


def pending_step():
    return {
        "orderNo": 1,
        "stepName": "选择格式",
        "keyword": "click",
        "locatorType": None,
        "locatorValue": None,
        "enabled": True,
        "continueOnFailure": False,
        "missingFields": [
            {
                "fields": ["locatorType", "locatorValue"],
                "operation": "选择格式",
                "target": "LeRobot选项",
                "value": "LeRobot",
                "reason": "需要选项定位",
            }
        ],
    }


def payload(step):
    return {"name": "格式选择", "enabled": True, "orderNo": 1, "stepsJson": [step]}


@pytest.mark.parametrize("enabled", [True, False])
def test_import_rejects_unresolved_even_disabled(enabled):
    step = pending_step()
    step["enabled"] = enabled
    with pytest.raises(AppError, match="待补充"):
        validate_ui_import_payload(payload(step))


def test_user_fills_same_yaml_without_regeneration():
    step = pending_step()
    step.update(locatorType="css", locatorValue='[data-format="LeRobot"]', missingFields=[])
    result = validate_ui_import_payload(payload(step))
    assert result[0]["stepsJson"][0]["locatorValue"] == '[data-format="LeRobot"]'
    assert "missingFields" not in result[0]["stepsJson"][0]


def test_deleting_metadata_does_not_fill_required_fields():
    step = pending_step()
    step.pop("missingFields")
    with pytest.raises(AppError, match="locatorType"):
        validate_ui_import_payload(payload(step))


@pytest.mark.parametrize("invalid", [None, {}, "missing"])
def test_malformed_missing_metadata_is_rejected(invalid):
    step = pending_step()
    step["missingFields"] = invalid
    with pytest.raises(AppError, match="必须是数组"):
        validate_ui_import_payload(payload(step))


@pytest.mark.asyncio
@pytest.mark.parametrize("suite", [False, True])
async def test_run_rejects_before_enqueue_or_commit(suite):
    repository = Mock()
    repository.list_cases = AsyncMock(return_value=[SimpleNamespace(steps_json=[pending_step()])])
    repository.commit = AsyncMock()
    service = UiTestCaseRunService(repository)
    service.get_accessible_case = AsyncMock(
        return_value=SimpleNamespace(case=SimpleNamespace(steps_json=[pending_step()]))
    )
    service.get_accessible_suite = AsyncMock(return_value=SimpleNamespace())
    with pytest.raises(AppError, match="待补充"):
        if suite:
            await service.run_suite("u", "s", RunUiSuiteRequest(environmentId="env"))
        else:
            await service.debug_run_case("u", "c", DebugRunUiCaseRequest(environmentId="env"))
    repository.add_all.assert_not_called()
    repository.commit.assert_not_awaited()
