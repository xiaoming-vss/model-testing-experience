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
from testing_agent_ai_worker.platform.http_client import lease_rejected
from testing_agent_ai_worker.platform.result_sink import ResultSink
from testing_agent_ai_worker.worker.lifecycle import WorkerLifecycle
from testing_agent_ai_worker.worker.outbox import OutboxDrain, ResultOutbox

LOGGER = logging.getLogger(__name__)


class LeaseLostError(RuntimeError):
    """Raised at a progress checkpoint after the task lease is gone."""


class _LeaseState:
    """Track heartbeat success and the local lease deadline for one task.

    The window runs from the moment a renewal request was sent. The control plane
    renews sometime before its answer arrives, so this window is never later than the
    control plane's own, and an answer that arrives after the window cannot revive it.
    """

    def __init__(
        self,
        *,
        lease_seconds: int,
        max_failures: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.lease_seconds = max(1, lease_seconds)
        self.max_failures = max(1, max_failures)
        self._clock = clock
        self._lock = threading.Lock()
        self._renewed_monotonic = clock()
        self._renewed_at = datetime.now(UTC)
        self._failures = 0
        self._lost = False

    def record_success(self, renewed_at: float) -> None:
        """Start a new window at ``renewed_at``, the moment the request was sent."""
        with self._lock:
            if self._lost:
                return
            if renewed_at < self._renewed_monotonic:
                # A newer renewal already moved the window; this older answer
                # must not shorten it or declare the lease lost.
                return
            elapsed = self._clock() - renewed_at
            if elapsed >= self.lease_seconds:
                # The answer outlived the window it was meant to extend.
                self._lost = True
                return
            self._renewed_monotonic = renewed_at
            self._renewed_at = datetime.now(UTC) - timedelta(seconds=max(0.0, elapsed))
            self._failures = 0

    def record_failure(self, *, rejected: bool = False) -> tuple[int, bool]:
        """Count a failed renewal; ``rejected`` means the control plane ended the attempt."""
        with self._lock:
            self._failures += 1
            lost = (
                rejected
                or self._failures >= self.max_failures
                or self._elapsed() >= self.lease_seconds
            )
            self._lost = self._lost or lost
            return self._failures, self._lost

    def lose(self) -> None:
        with self._lock:
            self._lost = True

    @property
    def lost(self) -> bool:
        # Read on every checkpoint, so a heartbeat that hangs past the deadline is caught
        # here without waiting for its failure to come back.
        with self._lock:
            return self._lost or self._elapsed() >= self.lease_seconds

    def lease_expires_at(self) -> datetime:
        with self._lock:
            return self._renewed_at + timedelta(seconds=self.lease_seconds)

    def remaining_seconds(self) -> float:
        with self._lock:
            return max(0.0, self.lease_seconds - self._elapsed())

    def _elapsed(self) -> float:
        return self._clock() - self._renewed_monotonic


def _lose_lease(
    task: Task, lease_lost_event: threading.Event, lease_state: _LeaseState, reason: str
) -> None:
    lease_state.lose()
    lease_lost_event.set()
    LOGGER.error(
        "task lease lost: task_id=%s attempt_id=%s %s",
        task.task_id,
        task.attempt_id,
        reason,
    )


def _status_of(error: BaseException) -> object:
    return getattr(getattr(error, "response", None), "status_code", None)


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
        result_sink: ResultSink,
        lifecycle: WorkerLifecycle,
        outbox: ResultOutbox | None = None,
        heartbeat_max_failures: int = 3,
    ) -> None:
        self.executor = executor
        self.result_sink = result_sink
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
            requested_at = time.monotonic()
            try:
                self.result_sink.submit_progress(
                    progress, timeout_seconds=lease_state.remaining_seconds() / 2
                )
            except Exception as exc:
                if lease_rejected(exc):
                    # The control plane ended this attempt: stop at this checkpoint.
                    _lose_lease(
                        task,
                        lease_lost_event,
                        lease_state,
                        f"progress_rejected status={_status_of(exc)}",
                    )
                    raise LeaseLostError("任务租约已失效") from None
                LOGGER.warning(
                    "progress submission failed: task_id=%s stage=%s error_type=%s status=%s\n%s",
                    progress.task_id,
                    progress.current_stage,
                    type(exc).__name__,
                    _status_of(exc),
                    safe_traceback(exc),
                )
            else:
                # Progress extends the platform lease for every AI queue path.
                lease_state.record_success(requested_at)
                if lease_state.lost:
                    _lose_lease(task, lease_lost_event, lease_state, "late_progress")
                    raise LeaseLostError("任务租约已失效") from None

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
            requested_at = time.monotonic()
            self.result_sink.mark_started(
                task.task_id,
                task.attempt_id,
                started_at.isoformat(),
                timeout_seconds=lease_state.remaining_seconds() / 2,
            )
            lease_state.record_success(requested_at)
            if lease_state.lost:
                # started was accepted after the window it was meant to extend:
                # never start work the control plane may already have reclaimed.
                _lose_lease(task, lease_lost_event, lease_state, "late_start")
                result = None
            else:
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
            if lease_rejected(exc):
                # The attempt was stopped or reclaimed before anything ran.
                _lose_lease(
                    task,
                    lease_lost_event,
                    lease_state,
                    f"start_rejected status={_status_of(exc)}",
                )
                result = None
            else:
                result = self._execution_error(task, exc, latest_progress, started_at)
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

    def _execution_error(
        self,
        task: Task,
        exc: Exception,
        latest_progress: TaskProgress | None,
        started_at: datetime,
    ) -> TaskResult:
        LOGGER.error(
            "task execution failed: task_id=%s error_type=%s\n%s",
            task.task_id,
            type(exc).__name__,
            safe_traceback(exc),
        )
        return TaskResult(
            task_id=task.task_id,
            attempt_id=task.attempt_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.ERROR,
            intermediate_json_text=(
                latest_progress.intermediate_json_text
                if latest_progress is not None
                else task.config_json
            ),
            result_summary_json=(
                latest_progress.result_summary_json if latest_progress is not None else ""
            ),
            # Provider messages may contain prompts, source text or credentials.
            error_message=safe_execution_error(exc),
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )

    def _submit_result(
        self,
        task: Task,
        result: TaskResult,
        lease_state: _LeaseState,
    ) -> None:
        try:
            self.result_sink.submit_result(result)
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
                outcome = self.outbox.drain(self.result_sink.submit_result)
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
            requested_at = time.monotonic()
            try:
                # Give up while half the lease is left, so another beat can still renew it.
                self.result_sink.send_heartbeat(
                    task.task_id,
                    task.attempt_id,
                    datetime.now().astimezone().isoformat(),
                    timeout_seconds=lease_state.remaining_seconds() / 2,
                )
            except Exception as exc:
                rejected = lease_rejected(exc)
                failures, lost = lease_state.record_failure(rejected=rejected)
                LOGGER.warning(
                    "task heartbeat failed: task_id=%s attempt_id=%s failures=%s "
                    "error_type=%s status=%s\n%s",
                    task.task_id,
                    task.attempt_id,
                    failures,
                    type(exc).__name__,
                    _status_of(exc),
                    safe_traceback(exc),
                )
                if lost:
                    reason = (
                        f"heartbeat_rejected status={_status_of(exc)}"
                        if rejected
                        else f"failures={failures}"
                    )
                    _lose_lease(task, lease_lost_event, lease_state, reason)
                    return
                # A failed renewal must not consume the whole remaining lease;
                # retry sooner, but never turn failures into an unbounded loop.
                wait_seconds = min(
                    interval_seconds,
                    max(0.1, lease_state.remaining_seconds() / 2),
                )
            else:
                lease_state.record_success(requested_at)
                if lease_state.lost:
                    _lose_lease(task, lease_lost_event, lease_state, "late_heartbeat")
                    return
                wait_seconds = interval_seconds
