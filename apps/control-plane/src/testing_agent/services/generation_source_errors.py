"""Translate generation source failures without exposing internal snapshots."""

from testing_agent.core.errors import AppError, ErrBadRequest, dynamic_error
from testing_agent.domain.generation_source_closure import SourceClosureError

_MESSAGES = {
    "pending_upstream": "所需阶段尚未采用内容",
    "source_stale": "来源或目标已变化，请重新确认",
    "source_unknown": "来源信息不完整或不可用，请重新生成",
    "source_conflict": "所选来源或目标不一致，请刷新后重试",
    "concurrent_change": "内容、来源或目标已变化，请刷新后重试",
}


def source_error(reason: str) -> AppError:
    """Map known closure reasons to safe, actionable business errors."""
    return dynamic_error(
        ErrBadRequest, _MESSAGES.get(reason, _MESSAGES["source_unknown"]), {"reason": reason}
    )


def closure_error(error: SourceClosureError) -> AppError:
    return source_error(error.reason)
