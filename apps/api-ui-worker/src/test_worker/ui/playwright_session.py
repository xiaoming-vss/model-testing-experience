"""Bound shutdown of the Playwright driver owned by one UI execution."""

import asyncio
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Any

from ..core import logger

DRIVER_STOP_TIMEOUT_SECONDS = 3.0
DRIVER_START_TIMEOUT_SECONDS = 45.0
DRIVER_HANDLE_WAIT_SECONDS = 3.0
DRIVER_LATE_REAP_SECONDS = 45.0
_late_reapers: set[asyncio.Task[None]] = set()


def _consume_result(task: asyncio.Future[Any]) -> None:
    with suppress(Exception, asyncio.CancelledError):
        task.result()


def _owned_driver(manager: Any) -> Any:
    connection = getattr(manager, "_connection", None)
    transport = getattr(connection, "_transport", None)
    return getattr(transport, "_proc", None)


def _kill_owned_driver(manager: Any) -> bool:
    """Stop only this context manager's subprocess, never an arbitrary PID.

    Playwright 1.60 has no public force-stop API. Keep its private transport
    access confined here and revalidate it whenever the locked version changes.
    """
    process = _owned_driver(manager)
    if process is None:
        return False
    try:
        if process.returncode is None:
            process.kill()
        return True
    except (ProcessLookupError, OSError):
        return False


async def _reap_late_driver(manager: Any, task_id: str) -> None:
    """Catch a subprocess that appears after startup could not be confirmed."""
    deadline = asyncio.get_running_loop().time() + DRIVER_LATE_REAP_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        process = _owned_driver(manager)
        if process is not None:
            if _kill_owned_driver(manager):
                try:
                    await asyncio.wait_for(process.wait(), DRIVER_STOP_TIMEOUT_SECONDS)
                    logger.warn("late playwright driver reaped", {"taskId": task_id})
                    return
                except (Exception, asyncio.CancelledError):
                    break
            break
        await asyncio.sleep(0.05)
    logger.warn("late playwright driver could not be confirmed", {"taskId": task_id})


async def _abort_driver_start(
    manager: Any, starting: asyncio.Task[Any], task_id: str
) -> None:
    """Reap an initialized driver before reporting timeout or cancellation."""
    process = _owned_driver(manager)
    deadline = asyncio.get_running_loop().time() + DRIVER_HANDLE_WAIT_SECONDS
    while process is None and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.05)
        process = _owned_driver(manager)
    if process is None:
        reaper = asyncio.create_task(_reap_late_driver(manager, task_id))
        _late_reapers.add(reaper)
        reaper.add_done_callback(_late_reapers.discard)
    if process is None or not _kill_owned_driver(manager):
        starting.cancel()
        starting.add_done_callback(_consume_result)
        raise RuntimeError("无法确认浏览器驱动已退出，请检查 Worker 状态")
    try:
        await asyncio.wait_for(process.wait(), DRIVER_STOP_TIMEOUT_SECONDS)
    except (Exception, asyncio.CancelledError):
        starting.add_done_callback(_consume_result)
        raise RuntimeError("浏览器驱动未能退出，请检查 Worker 状态") from None
    try:
        await asyncio.wait_for(asyncio.shield(starting), DRIVER_STOP_TIMEOUT_SECONDS)
    except TimeoutError:
        starting.cancel()
        starting.add_done_callback(_consume_result)
    except Exception:
        # Driver termination normally makes the startup request fail.
        pass
    else:
        # Startup may race with cancellation; release the completed manager.
        with suppress(Exception):
            await asyncio.wait_for(
                manager.__aexit__(None, None, None), DRIVER_STOP_TIMEOUT_SECONDS
            )


@asynccontextmanager
async def playwright_session(
    factory: Callable[[], Any], task_id: str
) -> AsyncIterator[Any]:
    manager = factory()
    starting = asyncio.create_task(manager.__aenter__())
    try:
        playwright = await asyncio.wait_for(
            asyncio.shield(starting), DRIVER_START_TIMEOUT_SECONDS
        )
    except TimeoutError:
        await _abort_driver_start(manager, starting, task_id)
        raise TimeoutError("浏览器驱动启动超时，请检查 Worker 资源后手动重试") from None
    except asyncio.CancelledError:
        await _abort_driver_start(manager, starting, task_id)
        raise
    try:
        yield playwright
    finally:
        prior_error = sys.exc_info()[0] is not None
        stopping = asyncio.create_task(manager.__aexit__(None, None, None))
        failed = False
        try:
            await asyncio.wait_for(
                asyncio.shield(stopping), DRIVER_STOP_TIMEOUT_SECONDS
            )
        except TimeoutError:
            failed = True
            killed = _kill_owned_driver(manager)
            logger.warn(
                "playwright driver stop timed out",
                {"taskId": task_id, "driverKilled": killed},
            )
            try:
                await asyncio.wait_for(
                    asyncio.shield(stopping), DRIVER_STOP_TIMEOUT_SECONDS
                )
            except TimeoutError:
                stopping.add_done_callback(_consume_result)
                raise RuntimeError("浏览器驱动未能退出，请检查 Worker 状态") from None
            except asyncio.CancelledError:
                stopping.add_done_callback(_consume_result)
                raise
            except Exception:
                raise RuntimeError("浏览器驱动退出失败，请检查 Worker 状态") from None
        except asyncio.CancelledError:
            _kill_owned_driver(manager)
            stopping.add_done_callback(_consume_result)
            raise
        except Exception as error:
            failed = True
            logger.warn(
                "playwright driver stop failed",
                {"taskId": task_id, "errorType": type(error).__name__},
            )
            if not _kill_owned_driver(manager):
                raise RuntimeError("浏览器驱动退出失败，请检查 Worker 状态") from None
            try:
                await asyncio.wait_for(
                    _owned_driver(manager).wait(), DRIVER_STOP_TIMEOUT_SECONDS
                )
            except (Exception, asyncio.CancelledError):
                raise RuntimeError("浏览器驱动未能退出，请检查 Worker 状态") from None
        if failed and not prior_error:
            raise RuntimeError("浏览器驱动关闭异常，请检查 Worker 资源后手动重试")
