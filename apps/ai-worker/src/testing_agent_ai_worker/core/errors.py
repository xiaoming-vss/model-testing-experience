"""Safe exception rendering for worker logs and task results.

Worker exceptions can carry model prompts, source documents, repository content
or credentials in their message. Only the exception type, a source-only
traceback and task/attempt identifiers may cross the logging or reporting
boundary.
"""

from __future__ import annotations

import traceback

from pydantic import ValidationError

SAFE_EXECUTION_ERROR = "任务执行失败，请查看 Worker 日志"
SAFE_CREDENTIAL_ERROR = "获取 LLM 凭证失败，请检查模型授权"
SAFE_VALIDATION_HINT = "请检查字段格式或联系平台维护者"


class ConfigError(RuntimeError):
    """Settings could not be loaded; the message is safe to print."""


def exception_type(exc: BaseException) -> str:
    return type(exc).__name__


def safe_traceback(exc: BaseException) -> str:
    """Return file/line/function frames only; messages and source text are excluded."""
    frames = traceback.StackSummary.extract(
        traceback.walk_tb(exc.__traceback__),
        lookup_lines=False,
    )
    lines = [f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}' for frame in frames]
    return "\n".join(lines) + ("\n" if lines else "")


def safe_execution_error(exc: BaseException) -> str:
    return f"{exception_type(exc)}: {SAFE_EXECUTION_ERROR}"


def safe_credential_error(exc: BaseException) -> str:
    return f"{exception_type(exc)}: {SAFE_CREDENTIAL_ERROR}"


def safe_validation_summary(exc: ValidationError) -> str:
    """Format field paths and validator messages without input values."""
    parts: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        location = ".".join(str(item) for item in error.get("loc", ())) or "$"
        message = str(error.get("msg", "invalid value"))
        parts.append(f"{location}: {message}")
    return "; ".join(parts[:8]) or "validation failed"


def safe_validation_error(exc: ValidationError, *, subject: str) -> str:
    return f"{subject}: {safe_validation_summary(exc)}；{SAFE_VALIDATION_HINT}"
