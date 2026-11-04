"""
任务轮询器模块
轮询领取待执行任务
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Literal
from contextlib import suppress

from ..api.case_runner import ApiCaseRunner
from ..api.collection_runner import ApiCollectionRunner
from ..contracts.types import (
    UiCaseRunResult,
    UiSuiteRunResult,
    UiTaskHeartbeatPayload,
    UiTaskStartedPayload,
    UiWorkerTask,
    WorkerConfig,
)
from ..control_plane.client import (
    ControlPlaneClient,
    ExecutionLeaseLost,
    is_execution_rejected,
)
from ..core import logger
from ..ui.case_runner import UiCaseRunner
from ..ui.suite_runner import UiSuiteRunner
from .task_notifications import listen_for_tasks, publish_worker_presence, wait_for_task


def _now_iso() -> str:
    """获取当前时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()


def _fallback_wait_seconds(interval_ms: int) -> float:
    """Spread idle checks without delaying event-driven wakeups."""
    return interval_ms / 1000 * random.uniform(0.9, 1.1)


class UserStopped(Exception):
    """A user requested cancellation of the current task."""


class TaskPoller:
    """任务轮询器类"""

    def __init__(
        self,
        config: WorkerConfig,
        control_plane_client: ControlPlaneClient,
        case_runner: UiCaseRunner,
        suite_runner: UiSuiteRunner,
    ) -> None:
        """
        初始化任务轮询器

        Args:
            config: 工作配置
            control_plane_client: 控制面客户端
            case_runner: 用例运行器
            suite_runner: 测试集运行器
        """
        self._config = config
        self._busy = asyncio.Event()
        self._presence_refresh = asyncio.Event()
        self._finishing_tasks: set[str] = set()
        self._control_plane_client = control_plane_client
        self._case_runner = case_runner
        self._suite_runner = suite_runner
        self._api_case_runner = ApiCaseRunner()
        self._api_collection_runner = ApiCollectionRunner(
            control_plane_client, self._api_case_runner
        )

    async def start(self) -> None:
        """开始轮询任务"""
        logger.info(
            "test worker poller started",
            {
                "workerId": self._config.worker_id,
                "mode": self._config.mode,
                "pollIntervalMs": self._config.poll_interval_ms,
            },
        )

        wake = asyncio.Event()
        redis_url = getattr(self._config, "redis_url", "")
        listener = (
            asyncio.create_task(listen_for_tasks(redis_url, wake))
            if redis_url
            else None
        )
        presence = (
            asyncio.create_task(
                publish_worker_presence(
                    redis_url,
                    self._config.worker_id,
                    self._busy,
                    self._presence_refresh,
                )
            )
            if redis_url
            else None
        )
        try:
            await self._poll(wake)
        finally:
            for background in (listener, presence):
                if background is not None:
                    background.cancel()
                    with suppress(asyncio.CancelledError):
                        await background

    async def _run_claimed(self, handler, task) -> None:
        self._busy.set()
        self._presence_refresh.set()
        try:
            await handler(task)
        finally:
            self._busy.clear()
            self._presence_refresh.set()

    async def _poll(self, wake: asyncio.Event) -> None:
        # One claimed task at a time bounds browser/HTTP resource usage. Alternate
        # the first queue checked so continuous UI traffic cannot starve API runs.
        api_first = False
        while True:
            try:
                # Clear before checking queues so a concurrent notification is not lost.
                wake.clear()
                queues: tuple[str, ...] = ("api", "ui") if api_first else ("ui", "api")
                claimed = False
                if hasattr(self._control_plane_client, "claim_next_task"):
                    task = await asyncio.to_thread(
                        self._control_plane_client.claim_next_task
                    )
                    if task is not NotImplemented:
                        if task:
                            claimed = True
                            if task.get("domain") == "api":
                                await self._run_claimed(self._handle_api_task, task)
                            elif task.get("domain") == "ui":
                                await self._run_claimed(
                                    self._handle_task,
                                    UiWorkerTask(
                                        task_id=task.get("taskId", ""),
                                        task_type=task.get("taskType", "case_debug"),
                                        run_id=task.get("runId", ""),
                                        suite_id=task.get("suiteId", "") or "",
                                        case_id=task.get("caseId", "") or "",
                                        lease_seconds=task.get("leaseSeconds", 0),
                                    ),
                                )
                            else:
                                raise ValueError("invalid claimed task domain")
                        queues = ()
                for queue in queues:
                    if queue == "api":
                        api_task = await asyncio.to_thread(
                            self._control_plane_client.claim_api_task
                        )
                        if not api_task:
                            continue
                        api_first = False
                        claimed = True
                        await self._run_claimed(self._handle_api_task, api_task)
                    else:
                        ui_task = await asyncio.to_thread(
                            self._control_plane_client.claim_task
                        )
                        if not ui_task:
                            continue
                        api_first = True
                        claimed = True
                        await self._run_claimed(self._handle_task, ui_task)
                    break
                if not claimed:
                    await wait_for_task(
                        getattr(self._config, "redis_url", ""),
                        wake,
                        timeout=_fallback_wait_seconds(self._config.poll_interval_ms),
                    )
            except Exception as e:
                logger.error("poll loop error", {"error": str(e)})
                await asyncio.sleep(
                    _fallback_wait_seconds(self._config.poll_interval_ms)
                )

    async def _wait_for_stop(self, domain: str, task_id: str) -> None:
        wake = asyncio.Event()
        redis_url = getattr(self._config, "redis_url", "")
        listener = (
            asyncio.create_task(
                listen_for_tasks(redis_url, wake, f"mtx:api-ui:control:{task_id}")
            )
            if redis_url
            else None
        )
        try:
            while True:
                wake.clear()
                try:
                    if await asyncio.to_thread(
                        self._control_plane_client.task_stop_requested, domain, task_id
                    ):
                        return
                except Exception as error:
                    if is_execution_rejected(error):
                        raise ExecutionLeaseLost("执行租约已失效") from None
                    logger.warn("task stop check unavailable", {"taskId": task_id})
                try:
                    await asyncio.wait_for(wake.wait(), timeout=10)
                except TimeoutError:
                    pass
        finally:
            if listener:
                listener.cancel()
                with suppress(asyncio.CancelledError):
                    await listener

    async def _run_until_stopped(self, domain: str, task_id: str, operation):
        if not hasattr(self._control_plane_client, "task_stop_requested"):
            return await operation
        running = asyncio.create_task(operation)
        stopping = asyncio.create_task(self._wait_for_stop(domain, task_id))
        try:
            done, _ = await asyncio.wait(
                {running, stopping}, return_when=asyncio.FIRST_COMPLETED
            )
            if stopping in done:
                await stopping
                running.cancel()
                with suppress(asyncio.CancelledError):
                    await running
                raise UserStopped()
            return await running
        finally:
            for task in (running, stopping):
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def _report_completion(self, domain: str, task_id: str, result) -> None:
        self._finishing_tasks.add(task_id)
        try:
            callback = (
                self._control_plane_client.report_task_completed
                if domain == "ui"
                else self._control_plane_client.report_api_task_completed
            )
            await asyncio.to_thread(callback, task_id, result)
        finally:
            self._finishing_tasks.discard(task_id)

    async def _handle_task(self, task: UiWorkerTask) -> None:
        """
        处理任务

        Args:
            task: 工作任务
        """
        logger.info(
            "task claimed",
            {
                "taskId": task.task_id,
                "taskType": task.task_type,
                "runId": task.run_id,
            },
        )

        # 上报任务开始
        await asyncio.to_thread(
            self._control_plane_client.report_task_started,
            task.task_id,
            UiTaskStartedPayload(
                worker_id=self._config.worker_id,
                started_at=_now_iso(),
            ),
        )

        # 启动心跳定时器
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(task.task_id))

        try:
            # 获取任务快照
            snapshot = await asyncio.to_thread(
                self._control_plane_client.get_task_snapshot, task.task_id
            )
            logger.info(
                "ui task snapshot loaded",
                {
                    "taskId": task.task_id,
                    "taskType": task.task_type,
                },
            )

            result: UiCaseRunResult | UiSuiteRunResult
            if task.task_type == "case_debug":
                if not snapshot.case_run:
                    raise ValueError(f"task {task.task_id} 缺少 case_run 快照")
                result = await self._run_until_stopped(
                    "ui", task.task_id, self._case_runner.run(snapshot.case_run)
                )
            elif task.task_type == "suite_run":
                if not snapshot.suite_run:
                    raise ValueError(f"task {task.task_id} 缺少 suite_run 快照")
                result = await self._run_until_stopped(
                    "ui", task.task_id, self._suite_runner.run(snapshot.suite_run)
                )
            else:
                raise ValueError(f"未知任务类型: {task.task_type}")

            # 上报任务完成
            await self._report_completion("ui", task.task_id, result)
            logger.info(
                "task completed",
                {
                    "taskId": task.task_id,
                    "status": result.status,
                    "success": result.success,
                    "taskType": task.task_type,
                },
            )

        except UserStopped:
            await self._report_task_error(task, "用户已停止运行", status="canceled")
        except ExecutionLeaseLost:
            logger.warn("ui execution lease lost", {"taskId": task.task_id})
        except asyncio.CancelledError:
            logger.warn(
                "task canceled during worker shutdown",
                {
                    "taskId": task.task_id,
                    "taskType": task.task_type,
                },
            )
            await self._report_task_error(task, "worker shutting down")
            raise
        except Exception as e:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                logger.warn(
                    "task canceled during worker shutdown",
                    {
                        "taskId": task.task_id,
                        "taskType": task.task_type,
                        "error": str(e),
                    },
                )
                await self._report_task_error(task, "worker shutting down")
                raise asyncio.CancelledError() from e
            logger.error(
                "task execution error",
                {
                    "taskId": task.task_id,
                    "taskType": task.task_type,
                    "error": str(e),
                },
            )

            # 上报错误
            await self._report_task_error(task, str(e))

        finally:
            # 取消心跳定时器
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self, task_id: str) -> None:
        """
        心跳循环

        Args:
            task_id: 任务 ID
        """
        while True:
            try:
                await asyncio.sleep(self._config.heartbeat_interval_ms / 1000)
                await asyncio.to_thread(
                    self._control_plane_client.report_task_heartbeat,
                    task_id,
                    UiTaskHeartbeatPayload(
                        worker_id=self._config.worker_id,
                        heartbeat_at=_now_iso(),
                    ),
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                if task_id in self._finishing_tasks and getattr(
                    e, "status_code", None
                ) in {400, 404}:
                    break
                logger.warn(
                    "heartbeat error",
                    {
                        "taskId": task_id,
                        "error": str(e),
                    },
                )

    async def _report_task_error(
        self,
        task: UiWorkerTask,
        error_message: str,
        *,
        status: Literal["error", "canceled"] = "error",
    ) -> None:
        """
        上报任务错误

        Args:
            task: 工作任务
            error_message: 错误消息
        """
        try:
            result: UiCaseRunResult | UiSuiteRunResult
            if task.task_type == "suite_run":
                result = UiSuiteRunResult(
                    task_id=task.task_id,
                    run_id=task.run_id,
                    suite_id=task.suite_id,
                    status=status,
                    success=False,
                    started_at=_now_iso(),
                    finished_at=_now_iso(),
                    duration_ms=0,
                    error_message=error_message,
                )
            else:
                result = UiCaseRunResult(
                    task_id=task.task_id,
                    run_id=task.run_id,
                    case_id=task.case_id,
                    status=status,
                    success=False,
                    started_at=_now_iso(),
                    finished_at=_now_iso(),
                    duration_ms=0,
                    error_message=error_message,
                    step_results=[],
                )
            await self._report_completion("ui", task.task_id, result)
        except Exception as e:
            logger.error(
                "report task error failed",
                {
                    "taskId": task.task_id,
                    "error": str(e),
                },
            )

    async def _handle_api_task(self, task: dict) -> None:
        """处理 API 任务。"""
        task_id = task.get("taskId", "")
        task_type = task.get("taskType", "")
        logger.info(
            "api task claimed",
            {
                "taskId": task_id,
                "taskType": task_type,
                "runId": task.get("runId", ""),
            },
        )

        started_at = _now_iso()
        await asyncio.to_thread(
            self._control_plane_client.report_api_task_started, task_id, started_at
        )
        heartbeat_task = asyncio.create_task(self._api_heartbeat_loop(task_id))

        try:
            snapshot = await asyncio.to_thread(
                self._control_plane_client.get_api_task_snapshot, task_id
            )
            logger.info(
                "api task snapshot loaded",
                {
                    "taskId": task_id,
                    "taskType": task_type,
                },
            )
            if task_type == "api_case_debug":
                case_run = snapshot.get("caseRun")
                if not case_run:
                    raise ValueError(f"api task {task_id} 缺少 caseRun 快照")
                result = await self._run_until_stopped(
                    "api", task_id, self._api_case_runner.run(case_run)
                )
            elif task_type == "api_collection_run":
                collection_run = snapshot.get("collectionRun")
                if not collection_run:
                    raise ValueError(f"api task {task_id} 缺少 collectionRun 快照")
                result = await self._run_until_stopped(
                    "api", task_id, self._api_collection_runner.run(collection_run)
                )
            else:
                raise ValueError(f"未知 API 任务类型: {task_type}")

            await self._report_completion("api", task_id, result)
            logger.info(
                "api task completed",
                {
                    "taskId": task_id,
                    "taskType": task_type,
                    "status": result.get("status"),
                    "success": result.get("success"),
                },
            )
        except UserStopped:
            await self._report_api_task_error(
                task, "用户已停止运行", started_at, status="canceled"
            )
        except ExecutionLeaseLost:
            logger.warn("api execution lease lost", {"taskId": task_id})
        except asyncio.CancelledError:
            logger.warn(
                "api task canceled during worker shutdown",
                {
                    "taskId": task_id,
                    "taskType": task_type,
                },
            )
            await self._report_api_task_error(task, "worker shutting down", started_at)
            raise
        except Exception as e:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                logger.warn(
                    "api task canceled during worker shutdown",
                    {
                        "taskId": task_id,
                        "taskType": task_type,
                        "error": str(e),
                    },
                )
                await self._report_api_task_error(task, "worker shutting down", started_at)
                raise asyncio.CancelledError() from e
            logger.error(
                "api task execution error",
                {
                    "taskId": task_id,
                    "taskType": task_type,
                    "error": str(e),
                },
            )
            await self._report_api_task_error(task, str(e), started_at)
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _api_heartbeat_loop(self, task_id: str) -> None:
        """API 任务心跳循环。"""
        while True:
            try:
                await asyncio.sleep(self._config.heartbeat_interval_ms / 1000)
                await asyncio.to_thread(
                    self._control_plane_client.report_api_task_heartbeat,
                    task_id,
                    _now_iso(),
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                if task_id in self._finishing_tasks and getattr(
                    e, "status_code", None
                ) in {400, 404}:
                    break
                logger.warn(
                    "api heartbeat error",
                    {
                        "taskId": task_id,
                        "error": str(e),
                    },
                )

    async def _report_api_task_error(
        self, task: dict, error_message: str, started_at: str, *, status: str = "error"
    ) -> None:
        """上报 API 任务错误。"""
        try:
            finished_at = _now_iso()
            await self._report_completion(
                "api",
                task.get("taskId", ""),
                {
                    "taskId": task.get("taskId", ""),
                    "runId": task.get("runId", ""),
                    "collectionRunId": task.get("collectionRunId", ""),
                    "collectionId": task.get("collectionId", ""),
                    "caseId": task.get("caseId", ""),
                    "status": status,
                    "success": False,
                    "startedAt": started_at,
                    "finishedAt": finished_at,
                    "durationMs": 0,
                    "errorMessage": error_message,
                    "request": {},
                    "response": {"statusCode": 0, "headersJson": "{}", "body": ""},
                    "runtimeVarsJson": "{}",
                    "extractResults": [],
                    "assertResults": [],
                },
            )
        except Exception as e:
            logger.error(
                "report api task error failed",
                {
                    "taskId": task.get("taskId", ""),
                    "error": str(e),
                },
            )
