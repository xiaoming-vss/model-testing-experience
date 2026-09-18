"""
任务轮询器模块
轮询领取待执行任务
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone

from ..core import logger
from ..api.case_runner import ApiCaseRunner
from ..api.collection_runner import ApiCollectionRunner
from ..control_plane.client import ControlPlaneClient
from ..ui.case_runner import UiCaseRunner
from ..ui.suite_runner import UiSuiteRunner
from ..contracts.types import (
    UiCaseRunResult,
    UiSuiteRunResult,
    UiTaskHeartbeatPayload,
    UiTaskStartedPayload,
    UiWorkerTask,
    WorkerConfig,
)


def _now_iso() -> str:
    """获取当前时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()


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
        self._control_plane_client = control_plane_client
        self._case_runner = case_runner
        self._suite_runner = suite_runner
        self._api_case_runner = ApiCaseRunner()
        self._api_collection_runner = ApiCollectionRunner(control_plane_client, self._api_case_runner)

    async def start(self) -> None:
        """开始轮询任务"""
        logger.info("test worker poller started", {
            "workerId": self._config.worker_id,
            "mode": self._config.mode,
            "pollIntervalMs": self._config.poll_interval_ms,
        })

        while True:
            try:
                # 尝试领取 UI 任务
                task = self._control_plane_client.claim_task()
                if task:
                    await self._handle_task(task)
                    continue

                # 尝试领取 API 任务
                api_task = self._control_plane_client.claim_api_task()
                if api_task:
                    await self._handle_api_task(api_task)
                    continue

                if not task:
                    # 没有可用任务，等待后继续
                    await asyncio.sleep(self._config.poll_interval_ms / 1000)
                    continue

            except Exception as e:
                logger.error("poll loop error", {"error": str(e)})
                await asyncio.sleep(self._config.poll_interval_ms / 1000)

    async def _handle_task(self, task: UiWorkerTask) -> None:
        """
        处理任务

        Args:
            task: 工作任务
        """
        logger.info("task claimed", {
            "taskId": task.task_id,
            "taskType": task.task_type,
            "runId": task.run_id,
        })

        # 上报任务开始
        self._control_plane_client.report_task_started(task.task_id, UiTaskStartedPayload(
            worker_id=self._config.worker_id,
            started_at=_now_iso(),
        ))

        # 启动心跳定时器
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(task.task_id))

        try:
            # 获取任务快照
            snapshot = self._control_plane_client.get_task_snapshot(task.task_id)
            logger.info("ui task snapshot loaded", {
                "taskId": task.task_id,
                "taskType": task.task_type,
                "snapshot": asdict(snapshot),
            })

            if task.task_type == "case_debug":
                if not snapshot.case_run:
                    raise ValueError(f"task {task.task_id} 缺少 case_run 快照")
                result = await self._case_runner.run(snapshot.case_run)
            elif task.task_type == "suite_run":
                if not snapshot.suite_run:
                    raise ValueError(f"task {task.task_id} 缺少 suite_run 快照")
                result = await self._suite_runner.run(snapshot.suite_run)
            else:
                raise ValueError(f"未知任务类型: {task.task_type}")

            # 上报任务完成
            self._control_plane_client.report_task_completed(task.task_id, result)
            logger.info("task completed", {
                "taskId": task.task_id,
                "status": result.status,
                "success": result.success,
                "taskType": task.task_type,
            })

        except asyncio.CancelledError:
            logger.warn("task canceled during worker shutdown", {
                "taskId": task.task_id,
                "taskType": task.task_type,
            })
            await self._report_task_error(task, "worker shutting down")
            raise
        except Exception as e:
            logger.error("task execution error", {
                "taskId": task.task_id,
                "taskType": task.task_type,
                "error": str(e),
            })

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
                self._control_plane_client.report_task_heartbeat(task_id, UiTaskHeartbeatPayload(
                    worker_id=self._config.worker_id,
                    heartbeat_at=_now_iso(),
                ))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warn("heartbeat error", {
                    "taskId": task_id,
                    "error": str(e),
                })

    async def _report_task_error(self, task: UiWorkerTask, error_message: str) -> None:
        """
        上报任务错误

        Args:
            task: 工作任务
            error_message: 错误消息
        """
        try:
            if task.task_type == "suite_run":
                result = UiSuiteRunResult(
                    task_id=task.task_id,
                    run_id=task.run_id,
                    suite_id=task.suite_id,
                    status="error",
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
                    status="error",
                    success=False,
                    started_at=_now_iso(),
                    finished_at=_now_iso(),
                    duration_ms=0,
                    error_message=error_message,
                    step_results=[],
                )
            self._control_plane_client.report_task_completed(task.task_id, result)
        except Exception as e:
            logger.error("report task error failed", {
                "taskId": task.task_id,
                "error": str(e),
            })

    async def _handle_api_task(self, task: dict) -> None:
        """处理 API 任务。"""
        task_id = task.get("taskId", "")
        task_type = task.get("taskType", "")
        logger.info("api task claimed", {
            "taskId": task_id,
            "taskType": task_type,
            "runId": task.get("runId", ""),
        })

        started_at = _now_iso()
        self._control_plane_client.report_api_task_started(task_id, started_at)
        heartbeat_task = asyncio.create_task(self._api_heartbeat_loop(task_id))

        try:
            snapshot = self._control_plane_client.get_api_task_snapshot(task_id)
            logger.info("api task snapshot loaded", {
                "taskId": task_id,
                "taskType": task_type,
                "snapshot": snapshot,
            })
            if task_type == "api_case_debug":
                case_run = snapshot.get("caseRun")
                if not case_run:
                    raise ValueError(f"api task {task_id} 缺少 caseRun 快照")
                result = await self._api_case_runner.run(case_run)
            elif task_type == "api_collection_run":
                collection_run = snapshot.get("collectionRun")
                if not collection_run:
                    raise ValueError(f"api task {task_id} 缺少 collectionRun 快照")
                result = await self._api_collection_runner.run(collection_run)
            else:
                raise ValueError(f"未知 API 任务类型: {task_type}")

            self._control_plane_client.report_api_task_completed(task_id, result)
            logger.info("api task completed", {
                "taskId": task_id,
                "taskType": task_type,
                "status": result.get("status"),
                "success": result.get("success"),
            })
        except asyncio.CancelledError:
            logger.warn("api task canceled during worker shutdown", {
                "taskId": task_id,
                "taskType": task_type,
            })
            await self._report_api_task_error(task, "worker shutting down", started_at)
            raise
        except Exception as e:
            logger.error("api task execution error", {
                "taskId": task_id,
                "taskType": task_type,
                "error": str(e),
            })
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
                self._control_plane_client.report_api_task_heartbeat(task_id, _now_iso())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warn("api heartbeat error", {
                    "taskId": task_id,
                    "error": str(e),
                })

    async def _report_api_task_error(self, task: dict, error_message: str, started_at: str) -> None:
        """上报 API 任务错误。"""
        try:
            finished_at = _now_iso()
            self._control_plane_client.report_api_task_completed(task.get("taskId", ""), {
                "taskId": task.get("taskId", ""),
                "runId": task.get("runId", ""),
                "collectionRunId": task.get("collectionRunId", ""),
                "collectionId": task.get("collectionId", ""),
                "caseId": task.get("caseId", ""),
                "status": "error",
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
            })
        except Exception as e:
            logger.error("report api task error failed", {
                "taskId": task.get("taskId", ""),
                "error": str(e),
            })
