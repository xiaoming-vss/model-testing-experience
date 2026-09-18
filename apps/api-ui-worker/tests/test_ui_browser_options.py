from __future__ import annotations

from test_worker.contracts.types import UiSuiteSnapshot
from test_worker.ui.browser_options import (
    context_options_from_suite,
    default_step_timeout_from_suite,
    launch_options_from_suite,
    screenshot_policy_from_suite,
)


def test_launch_options_use_server_suite_settings() -> None:
    suite = UiSuiteSnapshot(
        suite_id="suite-1",
        name="suite",
        headless=False,
        slow_mo_ms=25,
    )

    assert launch_options_from_suite(suite) == {
        "headless": False,
        "slow_mo": 25,
    }


def test_launch_options_do_not_invent_local_defaults() -> None:
    assert launch_options_from_suite(None) == {}
    assert launch_options_from_suite(UiSuiteSnapshot(suite_id="suite-1", name="suite")) == {}


def test_context_options_use_server_suite_viewport() -> None:
    suite = UiSuiteSnapshot(
        suite_id="suite-1",
        name="suite",
        viewport_width=1366,
        viewport_height=768,
    )

    assert context_options_from_suite(suite) == {
        "viewport": {
            "width": 1366,
            "height": 768,
        },
    }


def test_default_step_timeout_uses_server_suite_setting() -> None:
    suite = UiSuiteSnapshot(
        suite_id="suite-1",
        name="suite",
        default_step_timeout_ms=30000,
    )

    assert default_step_timeout_from_suite(suite) == 30000
    assert default_step_timeout_from_suite(None) == 5000


def test_screenshot_policy_uses_server_suite_setting() -> None:
    assert screenshot_policy_from_suite(
        UiSuiteSnapshot(suite_id="suite-1", name="suite", screenshot_policy="after_each_step")
    ) == "after_each_step"
    assert screenshot_policy_from_suite(
        UiSuiteSnapshot(suite_id="suite-1", name="suite", screenshot_policy="never")
    ) == "never"
    assert screenshot_policy_from_suite(None) == "on_failure"
