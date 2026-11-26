"""Delivering finished results to the control plane.

A failed delivery is not an execution failure: it is never reported as an
``error`` result. The control plane ends the attempt through its lease state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class ReportDeliveryError(Exception):
    """Execution finished but its result or artifacts could not be delivered."""

    def __init__(self, task_id: str, error: BaseException) -> None:
        self.task_id = task_id
        self.error_type = type(error).__name__
        self.status_code = getattr(error, "status_code", None)
        message = (
            f"result delivery failed: task_id={task_id} error_type={self.error_type}"
        )
        if isinstance(self.status_code, int):
            message += f" status_code={self.status_code}"
        super().__init__(message)


async def deliver(task_id: str, report: Callable[..., Any], *args: Any) -> None:
    """Run one blocking report; any failure becomes a delivery error for ``task_id``."""
    try:
        await asyncio.to_thread(report, *args)
    except Exception as error:
        raise ReportDeliveryError(task_id, error) from error
