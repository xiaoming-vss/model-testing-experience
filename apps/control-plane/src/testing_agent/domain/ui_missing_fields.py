"""Pending UI authoring content must never become an executable test silently."""

from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrUiTestSuiteImportInvalid, dynamic_error


def require_complete_ui_steps(steps: Any, *, case_label: str = "") -> None:
    """Reject unresolved authoring metadata, even on disabled steps, before side effects."""
    if not isinstance(steps, list):
        return  # Existing schema/import validation owns non-array errors.
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue
        if {"dataBindings", "sourceRefs"}.intersection(step):
            raise dynamic_error(
                ErrUiTestSuiteImportInvalid, "UI 补全草稿必须先补齐数据并通过正式导入，不能直接执行"
            )
        if "missingFields" not in step:
            continue
        location = f"{case_label} 步骤 {index}".strip()
        pending = step["missingFields"]
        if not isinstance(pending, list):
            raise dynamic_error(
                ErrUiTestSuiteImportInvalid, f"{location} 的 missingFields 必须是数组"
            )
        if pending:
            raise dynamic_error(
                ErrUiTestSuiteImportInvalid,
                f"{location} 有 {len(pending)} 项待补充内容；请补齐字段并移除对应 missingFields，"
                "或删除不需要的步骤后再导入/执行",
            )
