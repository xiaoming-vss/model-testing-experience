"""Best-effort step progress; final results remain authoritative."""

import asyncio
from dataclasses import asdict
from typing import Any

from ..contracts.types import UiStepDefinition, UiStepRunResult
from ..core import logger
from ..control_plane.client import raise_if_lease_lost


async def report_steps(
    client: Any,
    task_id: str,
    item_id: str | None,
    completed: list[UiStepRunResult],
    current: UiStepDefinition | None = None,
    order: int = 0,
    started_at: str = "",
) -> None:
    if client is None:
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
        # Progress also carries artifact tickets: a 400/422 is a payload problem and
        # must not abandon the run, so only the control plane's lease rejection does.
        raise_if_lease_lost(error)
        # Progress must never re-execute or fail the step. The final callback
        # still reports all results and validates artifact references.
        logger.warn(
            "ui step progress unavailable",
            {
                "taskId": task_id,
                "errorType": type(error).__name__,
                "statusCode": getattr(error, "status_code", None),
            },
        )
