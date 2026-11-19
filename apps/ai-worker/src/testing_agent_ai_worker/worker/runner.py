"""Task execution lifecycle runner.

调用链路：
- `main._run_worker_iteration -> WorkerRunner.process_task`
- `process_task -> mark_started -> heartbeat thread -> executor.execute`
- `process_task -> submit_progress / submit completed`

这里把平台生命周期回调和真正的业务执行器串成一个完整闭环。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from testing_agent_ai_worker.core.errors import safe_execution_error, safe_traceback
from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.services.result_service import ResultService
from testing_agent_ai_worker.worker.lifecycle import WorkerLifecycle
from testing_agent_ai_worker.worker.outbox import OutboxDrain, ResultOutbox

LOGGER = logging.getLogger(__name__)


class LeaseLostError(RuntimeError):
    """Raised at a progress checkpoint after the task lease is gone."""


class _LeaseState:
    """Track heartbeat success and the local lease deadline for one task."""

    def __init__(self, *, lease_seconds: int, max_failures: int) -> None:
        self.lease_seconds = max(1, lease_seconds)
        self.max_failures = max(1, max_failures)
        self._lock = threading.Lock()
        self._last_success_monotonic = time.monotonic()
        self._last_success_at = datetime.now(UTC)
        self._failures = 0
        self._lost = False

    def record_success(self) -> None:
        with self._lock:
            if self._lost:
                return
            self._last_success_at = datetime.now(UTC)
            self._last_success_monotonic = time.monotonic()
            self._failures = 0

    def record_failure(self) -> tuple[int, bool]:
        with self._lock:
            self._failures += 1
            elapsed = time.monotonic() - self._last_success_monotonic
            if self._failures >= self.max_failures or elapsed >= self.lease_seconds:
                self._lost = True
            return self._failures, self._lost

    @property
    def lost(self) -> bool:
        with self._lock:
            return self._lost

    def lease_expires_at(self) -> datetime:
        with self._lock:
            return self._last_success_at + timedelta(seconds=self.lease_seconds)

    def remaining_seconds(self) -> float:
        with self._lock:
            elapsed = time.monotonic() - self._last_success_monotonic
            return max(0.0, self.lease_seconds - elapsed)


class TaskExecutor:
    """执行器协议。

    返回 `TaskResult` 表示本轮应提交 completed；
    返回 `None` 表示任务停在 checkpoint 中间阶段，只提交 progress。
    """

    def execute(
        self,
        task: Task,
        started_at: datetime,
        progress_callback: Callable[[TaskProgress], None],
    ) -> TaskResult | None: ...


class WorkerRunner:
    """生命周期执行编排器。"""

    def __init__(
        self,
        *,
        executor: TaskExecutor,
        result_service: ResultService,
        lifecycle: WorkerLifecycle,
        outbox: ResultOutbox | None = None,
        heartbeat_max_failures: int = 3,
    ) -> None:
        self.executor = executor
        self.result_service = result_service
        self.lifecycle = lifecycle
        self.outbox = outbox
        self.heartbeat_max_failures = max(1, heartbeat_max_failures)
        self._outbox_lock = threading.Lock()

    def process_task(self, task: Task) -> TaskResult | None:
        """执行单个任务并维护 started/heartbeat/completed。

        这里不关心具体业务类型，只负责统一生命周期包装。
        """

        self.recover_outbox()
        started_at = datetime.now().astimezone()
        stop_event = threading.Event()
        lease_lost_event = threading.Event()
        lease_state = _LeaseState(
            lease_seconds=task.lease_seconds,
            max_failures=self.heartbeat_max_failures,
        )
        heartbeat_thread: threading.Thread | None = None
        latest_progress: TaskProgress | None = None

        def submit_progress(progress: TaskProgress) -> None:
            nonlocal latest_progress
            if lease_lost_event.is_set() or lease_state.lost:
                raise LeaseLostError("任务租约已失效")
            latest_progress = progress
            try:
                self.result_service.submit_progress(progress)
            except Exception as exc:
                LOGGER.warning(
                    "progress submission failed: task_id=%s stage=%s error_type=%s\n%s",
                    progress.task_id,
                    progress.current_stage,
                    type(exc).__name__,
                    safe_traceback(exc),
                )
            else:
                # Progress extends the platform lease for every AI queue path.
                lease_state.record_success()

        # 凭证缺失属于执行前失败，直接回传 failed，不进入 started/heartbeat。
        if task.credential_error:
            result = TaskResult(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.FAILED,
                intermediate_json_text=task.config_json,
                error_message=task.credential_error,
                started_at=started_at,
                finished_at=started_at,
            )
            self._submit_result(task, result, lease_state)
            return result

        try:
            self.result_service.mark_started(task.task_id, task.attempt_id, started_at.isoformat())
            lease_state.record_success()
            heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                args=(task, stop_event, lease_lost_event, lease_state),
                daemon=True,
            )
            heartbeat_thread.start()

            try:
                result = self.executor.execute(
                    task,
                    started_at,
                    submit_progress,
                )
            except LeaseLostError:
                result = None
        except Exception as exc:
            LOGGER.error(
                "task execution failed: task_id=%s error_type=%s\n%s",
                task.task_id,
                type(exc).__name__,
                safe_traceback(exc),
            )
            intermediate_json_text = (
                latest_progress.intermediate_json_text
                if latest_progress is not None
                else task.config_json
            )
            result = TaskResult(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.ERROR,
                intermediate_json_text=intermediate_json_text,
                output_yaml=latest_progress.output_yaml if latest_progress is not None else "",
                result_summary_json=(
                    latest_progress.result_summary_json if latest_progress is not None else ""
                ),
                # Provider messages may contain prompts, source text or credentials.
                error_message=safe_execution_error(exc),
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
            )
        finally:
            stop_event.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=1)

        if lease_lost_event.is_set() or lease_state.lost:
            # The control plane retires the attempt; a late completion must not
            # race the next attempt or reopen a closed run.
            LOGGER.warning(
                "task lease lost, result discarded: task_id=%s attempt_id=%s",
                task.task_id,
                task.attempt_id,
            )
            return None

        # checkpoint 中间阶段会返回 None，此时只允许平台看到 progress，不提交 completed。
        if result is not None:
            self._submit_result(task, result, lease_state)
        return result

    def _submit_result(
        self,
        task: Task,
        result: TaskResult,
        lease_state: _LeaseState,
    ) -> None:
        try:
            self.result_service.submit(result)
        except Exception as exc:
            self._preserve_result(task, result, lease_state)
            # The task already ran; surface the lost delivery instead of
            # letting the lease expire without any diagnostic.
            LOGGER.error(
                "task result submission failed: task=%s attempt=%s error=%s",
                task.task_id,
                task.attempt_id,
                type(exc).__name__,
            )

    def _preserve_result(
        self,
        task: Task,
        result: TaskResult,
        lease_state: _LeaseState,
    ) -> None:
        if self.outbox is None:
            return
        try:
            path = self.outbox.save(result, lease_expires_at=lease_state.lease_expires_at())
        except OSError as exc:
            LOGGER.error(
                "task result outbox write failed: task=%s attempt=%s error=%s",
                task.task_id,
                task.attempt_id,
                type(exc).__name__,
            )
            return
        LOGGER.warning(
            "task result saved to outbox: task=%s attempt=%s path=%s",
            task.task_id,
            task.attempt_id,
            path,
        )

    def recover_outbox(self) -> OutboxDrain | None:
        """Retry results preserved by an earlier completion failure."""

        if self.outbox is None:
            return None
        with self._outbox_lock:
            try:
                outcome = self.outbox.drain(self.result_service.submit)
            except OSError as exc:
                LOGGER.error(
                    "result outbox recovery failed: error_type=%s",
                    type(exc).__name__,
                )
                return None
            if outcome.delivered or outcome.failed or outcome.expired or outcome.discarded:
                LOGGER.info(
                    "result outbox recovery: delivered=%s failed=%s expired=%s discarded=%s",
                    outcome.delivered,
                    outcome.failed,
                    outcome.expired,
                    outcome.discarded,
                )
            return outcome

    def _heartbeat_loop(
        self,
        task: Task,
        stop_event: threading.Event,
        lease_lost_event: threading.Event,
        lease_state: _LeaseState,
    ) -> None:
        """后台心跳续租循环。"""

        interval_seconds = self.lifecycle.heartbeat_interval_for(task.lease_seconds)
        wait_seconds = interval_seconds
        while not stop_event.wait(wait_seconds):
            try:
                self.result_service.send_heartbeat(
                    task.task_id,
                    task.attempt_id,
                    datetime.now().astimezone().isoformat(),
                )
            except Exception as exc:
                failures, lost = lease_state.record_failure()
                LOGGER.warning(
                    "task heartbeat failed: task_id=%s attempt_id=%s failures=%s error_type=%s\n%s",
                    task.task_id,
                    task.attempt_id,
                    failures,
                    type(exc).__name__,
                    safe_traceback(exc),
                )
                if lost:
                    lease_lost_event.set()
                    LOGGER.error(
                        "task lease lost: task_id=%s attempt_id=%s failures=%s",
                        task.task_id,
                        task.attempt_id,
                        failures,
                    )
                    return
                # A failed renewal must not consume the whole remaining lease;
                # retry sooner, but never turn failures into an unbounded loop.
                wait_seconds = min(
                    interval_seconds,
                    max(0.1, lease_state.remaining_seconds() / 2),
                )
            else:
                lease_state.record_success()
                wait_seconds = interval_seconds
