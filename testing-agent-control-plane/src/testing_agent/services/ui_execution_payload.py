from __future__ import annotations

from copy import deepcopy
from typing import Any

from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite


def ui_suite_payload(suite: UiTestSuite | Any | None) -> dict[str, Any]:
    if suite is None:
        return {}
    return {
        "suiteId": suite.suite_id,
        "name": suite.name,
        "headless": suite.headless,
        "slowMoMs": suite.slow_mo_ms,
        "viewportWidth": suite.viewport_width,
        "viewportHeight": suite.viewport_height,
        "defaultStepTimeoutMs": suite.default_step_timeout_ms,
        "screenshotPolicy": getattr(suite, "screenshot_policy", None) or "on_failure",
    }


def ui_case_payload(case: UiTestCase | Any | None) -> dict[str, Any]:
    if case is None:
        return {}
    steps_json = case.steps_json
    if not isinstance(steps_json, list):
        raise ValueError("stepsJson 必须是数组")
    return {
        "caseId": case.case_id,
        "suiteId": case.suite_id,
        "name": case.name,
        "enabled": case.enabled,
        "orderNo": case.order_no,
        "stepsJson": deepcopy(steps_json),
    }
