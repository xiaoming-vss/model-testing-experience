"""Drain Playwright operations when a user interrupts an active browser step."""

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
from typing import Any, TypeVar

from playwright.async_api import Page

from ..core import logger

T = TypeVar("T")
CLEANUP_TIMEOUT_SECONDS = 3.0
BROWSER_START_TIMEOUT_SECONDS = 45.0


def _consume_driver_result(task: asyncio.Future[Any]) -> None:
    """A timed-out driver call can still finish while the browser closes."""
    with suppress(Exception, asyncio.CancelledError):
        task.result()


async def await_browser_start(operation: Awaitable[T]) -> T:
    """Limit a launch request while leaving its reply for the driver to drain.

    The caller owns the surrounding Playwright context, which must be exited on
    timeout or cancellation to stop the driver and any browser it started.
    """
    pending = asyncio.ensure_future(operation)
    try:
        return await asyncio.wait_for(
            asyncio.shield(pending), BROWSER_START_TIMEOUT_SECONDS
        )
    except TimeoutError:
        pending.add_done_callback(_consume_driver_result)
        raise TimeoutError("浏览器启动超时，请检查 Worker 资源后手动重试") from None
    except asyncio.CancelledError:
        pending.add_done_callback(_consume_driver_result)
        raise


async def close_browser_resource(
    operation: Awaitable[object], task_id: str, resource: str
) -> bool:
    """Bound individual cleanup calls while allowing the driver to finish them.

    The caller must still close the browser and Playwright driver afterwards.
    Shielding the operation prevents an abandoned Playwright channel reply from
    logging sensitive external data after the timeout.
    """
    pending = asyncio.ensure_future(operation)
    try:
        await asyncio.wait_for(asyncio.shield(pending), CLEANUP_TIMEOUT_SECONDS)
        return True
    except TimeoutError:
        pending.add_done_callback(_consume_driver_result)
        logger.warn(
            "browser cleanup timed out", {"taskId": task_id, "resource": resource}
        )
        return False
    except asyncio.CancelledError:
        pending.add_done_callback(_consume_driver_result)
        raise
    except Exception as error:
        logger.warn(
            "browser cleanup failed",
            {
                "taskId": task_id,
                "resource": resource,
                "errorType": type(error).__name__,
            },
        )
        return False


async def await_browser_operation(operation: Awaitable[T], page: Page) -> T:
    """Close the context on cancellation and consume the driver's pending reply."""
    pending = asyncio.ensure_future(operation)
    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        # Cancelling Playwright's channel wait directly can leave an unobserved
        # driver future containing the target URL. Closing the context first
        # makes the in-flight operation fail normally, and we consume that error.
        with suppress(Exception):
            await asyncio.wait_for(page.context.close(), timeout=3)
        try:
            await asyncio.wait_for(asyncio.shield(pending), timeout=3)
        except (Exception, asyncio.CancelledError):
            pending.cancel()
            with suppress(Exception, asyncio.CancelledError):
                await pending
        raise
