"""
任务轮询器模块
轮询领取待执行任务
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timezone
from typing import Callable, Literal
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
    ControlPlaneRequestError,
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


DEFAULT_LEASE_SECONDS = 30.0


class TaskLease:
    """Local lease deadline; heartbeat success renews it, rejection ends it."""

    def __init__(
        self, lease_seconds: float, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.lease_seconds = max(0.01, float(lease_seconds))
        self._clock = clock
        self._deadline = clock() + self.lease_seconds
        self.renewed = asyncio.Event()
        self.lost = False

    def renew(self) -> None:
        if self.lost:
            return
        self._deadline = self._clock() + self.lease_seconds
        self.renewed.set()

    def expire(self) -> None:
        self.lost = True
        self.renewed.set()

    def remaining_seconds(self) -> float:
        return max(0.0, self._deadline - self._clock())

    def is_expired(self) -> bool:
        return self.lost or self.remaining_seconds() <= 0


class UserStopped(Exception):
    """A user requested cancellation of the current task."""


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

    async def _run_until_stopped(
        self, domain: str, task_id: str, operation, lease: TaskLease | None = None
    ):
        if (
            not hasattr(self._control_plane_client, "task_stop_requested")
            and lease is None
        ):
            return await operation
        running = asyncio.create_task(operation)
        stopping = (
            asyncio.create_task(self._wait_for_stop(domain, task_id))
            if hasattr(self._control_plane_client, "task_stop_requested")
            else None
        )
        lease_loss = (
            asyncio.create_task(self._wait_for_lease_loss(lease, task_id))
            if lease is not None
            else None
        )
        tasks = {running}
        if stopping is not None:
            tasks.add(stopping)
        if lease_loss is not None:
            tasks.add(lease_loss)
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if lease_loss is not None and lease_loss in done:
                await lease_loss
            if stopping is not None and stopping in done:
                await stopping
                running.cancel()
                with suppress(asyncio.CancelledError):
                    await running
                raise UserStopped()
            return await running
        finally:
            for task in tasks:
                if task.done():
                    # Consume a sibling's exception without masking the selected
                    # outcome (stop, lease loss or normal execution).
                    with suppress(asyncio.CancelledError):
                        task.exception()
                    continue
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def _wait_for_lease_loss(self, lease: TaskLease, task_id: str) -> None:
        while not lease.is_expired():
            remaining = lease.remaining_seconds()
            if remaining <= 0:
                break
            lease.renewed.clear()
            if lease.is_expired():
                break
            try:
                await asyncio.wait_for(lease.renewed.wait(), timeout=remaining)
            except TimeoutError:
                break
        if not lease.lost:
            logger.warn("task lease window expired", {"taskId": task_id})
        lease.expire()
        raise ExecutionLeaseLost("执行租约已失效")

    async def _report_completion(self, domain: str, task_id: str, result) -> None:
        self._finishing_tasks.add(task_id)
        try:
            callback = (
                self._control_plane_client.report_task_completed
                if domain == "ui"
                else self._control_plane_client.report_api_task_completed
            )
            await asyncio.to_thread(callback, task_id, result)
        except Exception as error:
            # The execution already finished. Reporting failure is not an
            # execution failure and must not synthesize a second error result.
            raise ReportDeliveryError(task_id, error) from error
        finally:
            self._finishing_tasks.discard(task_id)

    @staticmethod
    def _log_report_delivery_failure(
        domain: str,
        task_id: str,
        task_type: str,
        error: ReportDeliveryError,
    ) -> None:
        logger.error(
            f"{domain} task result delivery failed",
            {
                "taskId": task_id,
                "taskType": task_type,
                "errorType": error.error_type,
                "statusCode": error.status_code,
            },
        )

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

        lease = TaskLease(
            task.lease_seconds if task.lease_seconds > 0 else DEFAULT_LEASE_SECONDS
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
        lease.renew()

        # 启动心跳定时器
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(task.task_id, lease))

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
                    "ui",
                    task.task_id,
                    self._case_runner.run(snapshot.case_run),
                    lease=lease,
                )
            elif task.task_type == "suite_run":
                if not snapshot.suite_run:
                    raise ValueError(f"task {task.task_id} 缺少 suite_run 快照")
                result = await self._run_until_stopped(
                    "ui",
                    task.task_id,
                    self._suite_runner.run(snapshot.suite_run),
                    lease=lease,
                )
            else:
                raise ValueError(f"未知任务类型: {task.task_type}")

            # 上报任务完成；回传失败不等于执行失败，不合成 error 结果。
            try:
                await self._report_completion("ui", task.task_id, result)
            except ReportDeliveryError as error:
                self._log_report_delivery_failure(
                    "ui", task.task_id, task.task_type, error
                )
                return
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
            await self._report_task_error(
                task, "worker shutting down", status="canceled"
            )
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
                await self._report_task_error(
                    task, "worker shutting down", status="canceled"
                )
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

    async def _heartbeat_loop(self, task_id: str, lease: TaskLease) -> None:
        """
        心跳循环

        Args:
            task_id: 任务 ID
            lease: 本地租约窗口
        """
        while True:
            try:
                await asyncio.sleep(self._config.heartbeat_interval_ms / 1000)
                if task_id in self._finishing_tasks:
                    break
                await asyncio.to_thread(
                    self._control_plane_client.report_task_heartbeat,
                    task_id,
                    UiTaskHeartbeatPayload(
                        worker_id=self._config.worker_id,
                        heartbeat_at=_now_iso(),
                    ),
                )
                lease.renew()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if task_id in self._finishing_tasks and getattr(
                    e, "status_code", None
                ) in {400, 404}:
                    break
                if isinstance(e, ControlPlaneRequestError) and is_execution_rejected(e):
                    lease.expire()
                    logger.warn(
                        "task lease rejected",
                        {
                            "taskId": task_id,
                            "statusCode": e.status_code,
                        },
                    )
                    break
                logger.warn(
                    "heartbeat error",
                    {
                        "taskId": task_id,
                        "errorType": type(e).__name__,
                        "statusCode": getattr(e, "status_code", None),
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
        lease = TaskLease(task.get("leaseSeconds", 0) or DEFAULT_LEASE_SECONDS)
        await asyncio.to_thread(
            self._control_plane_client.report_api_task_started, task_id, started_at
        )
        lease.renew()
        heartbeat_task = asyncio.create_task(self._api_heartbeat_loop(task_id, lease))

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
                    "api",
                    task_id,
                    self._api_case_runner.run(case_run),
                    lease=lease,
                )
            elif task_type == "api_collection_run":
                collection_run = snapshot.get("collectionRun")
                if not collection_run:
                    raise ValueError(f"api task {task_id} 缺少 collectionRun 快照")
                result = await self._run_until_stopped(
                    "api",
                    task_id,
                    self._api_collection_runner.run(collection_run),
                    lease=lease,
                )
            else:
                raise ValueError(f"未知 API 任务类型: {task_type}")

            try:
                await self._report_completion("api", task_id, result)
            except ReportDeliveryError as error:
                self._log_report_delivery_failure("api", task_id, task_type, error)
                return
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
            await self._report_api_task_error(
                task, "worker shutting down", started_at, status="canceled"
            )
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
                await self._report_api_task_error(
                    task, "worker shutting down", started_at, status="canceled"
                )
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

    async def _api_heartbeat_loop(self, task_id: str, lease: TaskLease) -> None:
        """API 任务心跳循环。"""
        while True:
            try:
                await asyncio.sleep(self._config.heartbeat_interval_ms / 1000)
                if task_id in self._finishing_tasks:
                    break
                await asyncio.to_thread(
                    self._control_plane_client.report_api_task_heartbeat,
                    task_id,
                    _now_iso(),
                )
                lease.renew()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if task_id in self._finishing_tasks and getattr(
                    e, "status_code", None
                ) in {400, 404}:
                    break
                if isinstance(e, ControlPlaneRequestError) and is_execution_rejected(e):
                    lease.expire()
                    logger.warn(
                        "api task lease rejected",
                        {
                            "taskId": task_id,
                            "statusCode": e.status_code,
                        },
                    )
                    break
                logger.warn(
                    "api heartbeat error",
                    {
                        "taskId": task_id,
                        "errorType": type(e).__name__,
                        "statusCode": getattr(e, "status_code", None),
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
