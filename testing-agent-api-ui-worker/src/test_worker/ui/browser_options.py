"""Browser option helpers for UI worker snapshots."""

from __future__ import annotations

from typing import Any

from ..contracts.types import ScreenshotPolicy, UiSuiteSnapshot


def launch_options_from_suite(suite: UiSuiteSnapshot | None) -> dict[str, Any]:
    """Build Playwright launch options from server-provided suite settings."""
    options: dict[str, Any] = {}
    if suite is None:
        return options
    if suite.headless is not None:
        options["headless"] = suite.headless
    if suite.slow_mo_ms is not None:
        options["slow_mo"] = suite.slow_mo_ms
    return options


def context_options_from_suite(suite: UiSuiteSnapshot | None) -> dict[str, Any]:
    """Build Playwright browser context options from server-provided suite settings."""
    options: dict[str, Any] = {}
    if suite is None:
        return options
    if suite.viewport_width is not None and suite.viewport_height is not None:
        options["viewport"] = {
            "width": suite.viewport_width,
            "height": suite.viewport_height,
        }
    return options


def default_step_timeout_from_suite(suite: UiSuiteSnapshot | None, fallback_ms: int = 5000) -> int:
    """Resolve default step timeout from server-provided suite settings."""
    if suite and suite.default_step_timeout_ms:
        return suite.default_step_timeout_ms
    return fallback_ms


def screenshot_policy_from_suite(suite: UiSuiteSnapshot | None) -> ScreenshotPolicy:
    """Resolve screenshot policy from server-provided suite settings."""
    if suite and suite.screenshot_policy in ("on_failure", "after_each_step", "never"):
        return suite.screenshot_policy
    return "on_failure"
