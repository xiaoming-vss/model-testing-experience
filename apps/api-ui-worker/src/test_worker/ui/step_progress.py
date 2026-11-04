"""Best-effort step progress; final results remain authoritative."""

import asyncio
from dataclasses import asdict
from typing import Any

from ..contracts.types import UiStepDefinition, UiStepRunResult
from ..core import logger
from ..control_plane.client import ExecutionLeaseLost, is_execution_rejected


async def report_steps(
    client: Any,
    task_id: str,
    item_id: str | None,
    completed: list[UiStepRunResult],
    current: UiStepDefinition | None = None,
    order: int = 0,
    started_at: str = "",
) -> None:
    if client is None or not hasattr(client, "report_ui_steps"):
        return
    steps = [asdict(step) for step in completed]
    if current is not None:
        steps.append(
            {
                "order_no": order,
                "step_name": current.step_name or current.keyword,
                "keyword": current.keyword,
                "status": "running",
                "started_at": started_at,
            }
        )
    try:
        await asyncio.to_thread(client.report_ui_steps, task_id, item_id, steps)
    except Exception as error:
        if is_execution_rejected(error):
            raise ExecutionLeaseLost("执行租约已失效") from None
        # Progress must never re-execute or fail the step. The final callback
        # still reports all results and validates artifact references.
        logger.warn("ui step progress unavailable", {"taskId": task_id})
