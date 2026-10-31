from datetime import datetime
from typing import Any

from ..contracts.types import UiStepDefinition, UiStepRunResult
from .step_executor import now_iso


def build_failed_step_result(
    step: UiStepDefinition,
    fallback_order: int,
    started_at_iso: str,
    started_at: float,
    error_message: str,
    *,
    save_results: list[dict[str, Any]] | None = None,
    used_variables: list[dict[str, Any]] | None = None,
) -> "UiStepRunResult":
    """
    构建失败的步骤结果

    Args:
        step: 步骤定义
        fallback_order: 备用序号
        started_at_iso: 开始时间 ISO 格式
        started_at: 开始时间戳
        error_message: 错误消息
        save_results: 失败前已成功写回的提取结果
        used_variables: 失败前已引用的变量

    Returns:
        步骤运行结果
    """
    from ..contracts.types import UiStepRunResult

    step_name = step.step_name
    if not step_name or not step_name.strip():
        step_name = f"Step {fallback_order}"
    else:
        step_name = step_name.strip()

    return UiStepRunResult(
        order_no=step.order_no or fallback_order,
        step_name=step_name,
        keyword=step.keyword.lower(),
        status="failed",
        success=False,
        started_at=started_at_iso,
        finished_at=now_iso(),
        duration_ms=int((datetime.now().timestamp() - started_at) * 1000),
        error_message=error_message,
        save_results=list(save_results or []),
        used_variables=list(used_variables or []),
    )
