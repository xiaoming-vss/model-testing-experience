import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path

import httpx

from testing_agent_ai_worker.core.errors import UserFacingError
from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.platform.result_sink import ResultSink
from testing_agent_ai_worker.worker.lifecycle import WorkerLifecycle
from testing_agent_ai_worker.worker.outbox import ResultOutbox
from testing_agent_ai_worker.worker.runner import LeaseLostError, TaskExecutor, WorkerRunner
from tests.support.lifecycle import lifecycle


class _RecordingSink(ResultSink):
    def __init__(self) -> None:
        self.started_calls: list[tuple[str, str, str]] = []
        self.heartbeat_calls: list[tuple[str, str, str]] = []
        self.progress_calls: list[TaskProgress] = []
        self.result_calls: list[TaskResult] = []
        self.timeouts: list[tuple[str, float | None]] = []
        self.first_heartbeat = threading.Event()

    def mark_started(
        self,
        task_id: str,
        attempt_id: str,
        started_at_iso: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self.started_calls.append((task_id, attempt_id, started_at_iso))
        self.timeouts.append(("started", timeout_seconds))

    def send_heartbeat(
        self,
        task_id: str,
        attempt_id: str,
        heartbeat_at_iso: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self.heartbeat_calls.append((task_id, attempt_id, heartbeat_at_iso))
        self.timeouts.append(("heartbeat", timeout_seconds))
        self.first_heartbeat.set()

    def submit_progress(
        self, progress: TaskProgress, *, timeout_seconds: float | None = None
    ) -> None:
        self.progress_calls.append(progress)
        self.timeouts.append(("progress", timeout_seconds))

    def submit_result(self, result: TaskResult) -> None:
        self.result_calls.append(result)


class _FailingProgressSink(_RecordingSink):
    def submit_progress(
        self, progress: TaskProgress, *, timeout_seconds: float | None = None
    ) -> None:
        raise RuntimeError("progress endpoint unavailable")


class _FailingResultSink(_RecordingSink):
    def submit_result(self, result: TaskResult) -> None:
        raise RuntimeError("result endpoint unavailable")


class _FlakyResultSink(_RecordingSink):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next = True

    def submit_result(self, result: TaskResult) -> None:
        if self.fail_next:
            raise RuntimeError("SECRET-MARKER result endpoint unavailable")
        super().submit_result(result)


class _FailingHeartbeatSink(_RecordingSink):
    def send_heartbeat(
        self,
        task_id: str,
        attempt_id: str,
        heartbeat_at_iso: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        raise RuntimeError("SECRET-MARKER heartbeat endpoint unavailable")


class _FailingProgressAndHeartbeatSink(_FailingHeartbeatSink):
    def submit_progress(
        self, progress: TaskProgress, *, timeout_seconds: float | None = None
    ) -> None:
        raise RuntimeError("progress endpoint unavailable")


class _FlakyHeartbeatSink(_RecordingSink):
    def __init__(self, *, failures_before_success: int) -> None:
        super().__init__()
        self.failures_before_success = failures_before_success
        self.attempts = 0

    def send_heartbeat(
        self,
        task_id: str,
        attempt_id: str,
        heartbeat_at_iso: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self.attempts += 1
        if self.attempts <= self.failures_before_success:
            raise RuntimeError("heartbeat endpoint unavailable")
        super().send_heartbeat(
            task_id, attempt_id, heartbeat_at_iso, timeout_seconds=timeout_seconds
        )


def _rejected(status: int, method: str = "PATCH") -> httpx.HTTPStatusError:
    request = httpx.Request(method, "https://platform.example.test/internal/ai-worker/tasks/task-1")
    return httpx.HTTPStatusError(
        "SECRET-MARKER rejected", request=request, response=httpx.Response(status, request=request)
    )


class _RejectingSink(_RecordingSink):
    """Answer one lifecycle call with an HTTP error status."""

    def __init__(self, call: str, status: int) -> None:
        super().__init__()
        self.call = call
        self.status = status

    def _reject(self, call: str) -> None:
        if call == self.call:
            raise _rejected(self.status)

    def mark_started(self, task_id, attempt_id, started_at_iso, *, timeout_seconds=None) -> None:
        super().mark_started(task_id, attempt_id, started_at_iso, timeout_seconds=timeout_seconds)
        self._reject("started")

    def send_heartbeat(
        self, task_id, attempt_id, heartbeat_at_iso, *, timeout_seconds=None
    ) -> None:
        super().send_heartbeat(
            task_id, attempt_id, heartbeat_at_iso, timeout_seconds=timeout_seconds
        )
        self._reject("heartbeat")

    def submit_progress(self, progress, *, timeout_seconds=None) -> None:
        super().submit_progress(progress, timeout_seconds=timeout_seconds)
        self._reject("progress")


class _HangingHeartbeatSink(_RecordingSink):
    """A heartbeat that never gets an answer until the test releases it."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    def send_heartbeat(
        self,
        task_id: str,
        attempt_id: str,
        heartbeat_at_iso: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        super().send_heartbeat(
            task_id, attempt_id, heartbeat_at_iso, timeout_seconds=timeout_seconds
        )
        self.release.wait(timeout=10)


class _SlowAnswerHeartbeatSink(_RecordingSink):
    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay

    def send_heartbeat(
        self,
        task_id: str,
        attempt_id: str,
        heartbeat_at_iso: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        time.sleep(self.delay)
        super().send_heartbeat(
            task_id, attempt_id, heartbeat_at_iso, timeout_seconds=timeout_seconds
        )


class _SlowAnswerStartSink(_RecordingSink):
    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay

    def mark_started(
        self,
        task_id: str,
        attempt_id: str,
        started_at_iso: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        time.sleep(self.delay)
        super().mark_started(task_id, attempt_id, started_at_iso, timeout_seconds=timeout_seconds)


class _SlowAnswerProgressSink(_RecordingSink):
    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay

    def submit_progress(
        self, progress: TaskProgress, *, timeout_seconds: float | None = None
    ) -> None:
        time.sleep(self.delay)
        super().submit_progress(progress, timeout_seconds=timeout_seconds)


class _SlowProgressHangingHeartbeatSink(_HangingHeartbeatSink):
    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay

    def submit_progress(
        self, progress: TaskProgress, *, timeout_seconds: float | None = None
    ) -> None:
        time.sleep(self.delay)
        super().submit_progress(progress, timeout_seconds=timeout_seconds)


class _SuccessfulExecutor(TaskExecutor):
    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                current_stage="interface_extract",
                stage_status="running",
                intermediate_json_text='{"cases":[]}',
                result_summary_json='{"status":"running"}',
            )
        )
        return TaskResult(
            task_id=task.task_id,
            attempt_id=task.attempt_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.SUCCESS,
            intermediate_json_text='{"cases":[]}',
            output_yaml="cases: []",
            result_summary_json='{"status":"success"}',
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )


class _HeartbeatAwareExecutor(TaskExecutor):
    def __init__(self, sink: _RecordingSink) -> None:
        self.sink = sink

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        self.sink.first_heartbeat.wait(timeout=2.0)
        return TaskResult(
            task_id=task.task_id,
            attempt_id=task.attempt_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.SUCCESS,
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )


class _ExplodingExecutor(TaskExecutor):
    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        raise RuntimeError("executor boom")


class _BlankErrorExecutor(TaskExecutor):
    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        raise TimeoutError()


class _ProgressThenExplodingExecutor(TaskExecutor):
    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                current_stage="case_names",
                stage_status="running",
                intermediate_json_text='{"enhancedText":"progress text","caseNames":[]}',
                result_summary_json='{"status":"running","stage":"case_names"}',
            )
        )
        raise RuntimeError("executor boom after progress")


class _CheckpointPauseExecutor(TaskExecutor):
    def execute(self, task: Task, started_at: datetime, progress_callback) -> None:
        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                current_stage="requirement_analysis",
                stage_status="waiting_review",
                intermediate_json_text='{"enhancedText":"text"}',
                result_summary_json='{"status":"running"}',
            )
        )
        return None


class _LeaseCheckExecutor(TaskExecutor):
    """Keep producing progress until the runner reports lease loss."""

    def __init__(self, *, timeout_seconds: float = 2.0) -> None:
        self.timeout_seconds = timeout_seconds

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult | None:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            try:
                progress_callback(
                    TaskProgress(
                        task_id=task.task_id,
                        attempt_id=task.attempt_id,
                        current_stage="analyzing",
                        stage_status="running",
                    )
                )
            except LeaseLostError:
                return None
            time.sleep(0.005)
        return TaskResult(
            task_id=task.task_id,
            attempt_id=task.attempt_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.SUCCESS,
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )


class _SleepingExecutor(TaskExecutor):
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        time.sleep(self.seconds)
        return TaskResult(
            task_id=task.task_id,
            attempt_id=task.attempt_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.SUCCESS,
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )


class WorkerRunnerTests(unittest.TestCase):
    def _make_task(self) -> Task:
        return Task(
            task_id="task-1",
            attempt_id="run-1",
            generate_task_id="generate-1",
            task_type="api_case_generate",
            lease_seconds=1,
            config_json='{"enhancedText":"snapshot text"}',
            payload=TaskPayload(openapi_content="{}", source_content="{}"),
        )

    def test_process_task_marks_started_submits_progress_and_completed(self) -> None:
        sink = _RecordingSink()
        runner = WorkerRunner(
            executor=_SuccessfulExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(len(sink.started_calls), 1)
        self.assertEqual(sink.started_calls[0][1], "run-1")
        self.assertEqual(len(sink.progress_calls), 1)
        self.assertEqual(len(sink.result_calls), 1)
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(sink.progress_calls[0].current_stage, "interface_extract")

    def test_process_task_continues_when_progress_submission_fails(self) -> None:
        sink = _FailingProgressSink()
        runner = WorkerRunner(
            executor=_SuccessfulExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(1, len(sink.result_calls))
        self.assertEqual(TaskStatus.SUCCESS, sink.result_calls[0].status)

    def test_process_task_logs_result_submission_failure_without_raising(self) -> None:
        sink = _FailingResultSink()
        runner = WorkerRunner(
            executor=_SuccessfulExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(),
        )

        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="ERROR") as logs:
            result = runner.process_task(self._make_task())

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual([], sink.result_calls)
        self.assertIn("task=task-1 attempt=run-1 error=RuntimeError", "\n".join(logs.output))

    def test_process_task_sends_heartbeat_while_executor_is_running(self) -> None:
        sink = _RecordingSink()
        runner = WorkerRunner(
            executor=_HeartbeatAwareExecutor(sink),
            result_sink=sink,
            lifecycle=lifecycle(heartbeat_interval_seconds=1),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertGreaterEqual(len(sink.heartbeat_calls), 1)

    def test_process_task_turns_executor_error_into_final_error_result(self) -> None:
        sink = _RecordingSink()
        runner = WorkerRunner(
            executor=_ExplodingExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(result.status, TaskStatus.ERROR)
        self.assertEqual(result.error_message, "RuntimeError: 任务执行失败，请查看 Worker 日志")
        self.assertEqual(result.intermediate_json_text, '{"enhancedText":"snapshot text"}')
        self.assertEqual(sink.result_calls[0].status, TaskStatus.ERROR)
        self.assertEqual(
            sink.result_calls[0].intermediate_json_text, '{"enhancedText":"snapshot text"}'
        )

    def test_process_task_reports_a_user_facing_failure_as_written(self) -> None:
        class KnownFailureExecutor(TaskExecutor):
            def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
                raise UserFacingError(
                    "需求材料提取仅支持 Word/DOCX 或富文本，请替换原始需求文档后重试"
                )

        sink = _RecordingSink()
        runner = WorkerRunner(
            executor=KnownFailureExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(result.status, TaskStatus.ERROR)
        self.assertEqual(
            result.error_message, "需求材料提取仅支持 Word/DOCX 或富文本，请替换原始需求文档后重试"
        )

    def test_executor_error_log_and_result_omit_provider_message(self) -> None:
        class SecretExecutor(TaskExecutor):
            def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
                raise RuntimeError("SECRET-MARKER prompt and token")

        runner = WorkerRunner(
            executor=SecretExecutor(),
            result_sink=_RecordingSink(),
            lifecycle=lifecycle(),
        )

        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="ERROR") as logs:
            result = runner.process_task(self._make_task())

        output = "\n".join(logs.output)
        self.assertNotIn("SECRET-MARKER", output)
        self.assertNotIn("SECRET-MARKER", result.error_message or "")
        self.assertIn("RuntimeError", output)
        self.assertIn("RuntimeError", result.error_message or "")

    def test_process_task_never_publishes_a_blank_error_message(self) -> None:
        runner = WorkerRunner(
            executor=_BlankErrorExecutor(),
            result_sink=_RecordingSink(),
            lifecycle=lifecycle(),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(result.status, TaskStatus.ERROR)
        self.assertEqual(result.error_message, "TimeoutError: 任务执行失败，请查看 Worker 日志")

    def test_process_task_preserves_latest_progress_config_when_executor_errors_after_progress(
        self,
    ) -> None:
        sink = _RecordingSink()
        runner = WorkerRunner(
            executor=_ProgressThenExplodingExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(result.status, TaskStatus.ERROR)
        self.assertEqual(result.error_message, "RuntimeError: 任务执行失败，请查看 Worker 日志")
        self.assertEqual(
            result.intermediate_json_text, '{"enhancedText":"progress text","caseNames":[]}'
        )
        self.assertEqual(result.output_yaml, "")
        self.assertEqual(result.result_summary_json, '{"status":"running","stage":"case_names"}')

    def test_process_task_submits_failed_result_when_credentials_are_missing(self) -> None:
        sink = _RecordingSink()
        task = self._make_task()
        task.credential_error = "credentials unavailable"
        runner = WorkerRunner(
            executor=_ExplodingExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(),
        )

        result = runner.process_task(task)

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertIn("credentials unavailable", result.error_message or "")
        self.assertEqual(sink.started_calls, [])
        self.assertEqual(sink.heartbeat_calls, [])

    def test_process_task_does_not_submit_completed_when_executor_returns_none(self) -> None:
        sink = _RecordingSink()
        runner = WorkerRunner(
            executor=_CheckpointPauseExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(),
        )

        result = runner.process_task(self._make_task())

        self.assertIsNone(result)
        self.assertEqual(len(sink.started_calls), 1)
        self.assertEqual(len(sink.progress_calls), 1)
        self.assertEqual(sink.progress_calls[0].stage_status, "waiting_review")
        self.assertEqual(sink.result_calls, [])

    def test_heartbeat_failures_are_logged_and_stop_execution(self) -> None:
        sink = _FailingProgressAndHeartbeatSink()
        runner = WorkerRunner(
            executor=_LeaseCheckExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(heartbeat_interval_seconds=0.01),
            heartbeat_max_failures=3,
        )

        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
            result = runner.process_task(self._make_task())

        output = "\n".join(logs.output)
        self.assertIsNone(result)
        self.assertEqual([], sink.result_calls)
        self.assertIn("failures=1", output)
        self.assertIn("failures=3", output)
        self.assertIn("task lease lost", output)
        self.assertNotIn("SECRET-MARKER", output)

    def test_lease_deadline_stops_execution_even_below_failure_threshold(self) -> None:
        sink = _FailingProgressAndHeartbeatSink()
        runner = WorkerRunner(
            executor=_LeaseCheckExecutor(),
            result_sink=sink,
            lifecycle=lifecycle(heartbeat_interval_seconds=0.05),
            heartbeat_max_failures=100,
        )

        started = time.monotonic()
        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
            result = runner.process_task(self._make_task())

        elapsed = time.monotonic() - started
        self.assertIsNone(result)
        self.assertEqual([], sink.result_calls)
        self.assertGreaterEqual(elapsed, 0.9)
        self.assertIn("task lease lost", "\n".join(logs.output))

    def test_heartbeat_success_resets_failure_count(self) -> None:
        sink = _FlakyHeartbeatSink(failures_before_success=2)
        runner = WorkerRunner(
            executor=_SleepingExecutor(0.15),
            result_sink=sink,
            lifecycle=lifecycle(heartbeat_interval_seconds=0.01),
            heartbeat_max_failures=3,
        )

        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
            result = runner.process_task(self._make_task())

        self.assertIsNotNone(result)
        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertGreaterEqual(sink.attempts, 3)
        self.assertEqual(1, len(sink.result_calls))
        self.assertNotIn("task lease lost", "\n".join(logs.output))

    def _lease_runner(self, sink, executor, *, interval=0.01, max_failures=3) -> WorkerRunner:
        return WorkerRunner(
            executor=executor,
            result_sink=sink,
            lifecycle=lifecycle(heartbeat_interval_seconds=interval),
            heartbeat_max_failures=max_failures,
        )

    def test_lease_expires_while_a_heartbeat_is_still_waiting_for_its_answer(self) -> None:
        # No failure ever comes back, so only the clock can end the lease.
        sink = _HangingHeartbeatSink()
        runner = self._lease_runner(sink, _LeaseCheckExecutor(timeout_seconds=3), max_failures=100)

        try:
            with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
                result = runner.process_task(self._make_task())
        finally:
            sink.release.set()

        self.assertIsNone(result)
        self.assertEqual([], sink.result_calls)
        self.assertIn("task lease lost, result discarded", "\n".join(logs.output))
        # A hanging beat is cut off while half of the one-second lease is still left.
        self.assertTrue(sink.timeouts)
        self.assertTrue(
            all(0 < limit <= 0.5 for call, limit in sink.timeouts if call == "heartbeat")
        )

    def test_renewing_calls_are_bounded_by_the_remaining_lease(self) -> None:
        sink = _RecordingSink()
        runner = self._lease_runner(sink, _SuccessfulExecutor(), interval=60)

        self.assertIsNotNone(runner.process_task(self._make_task()))

        self.assertEqual(["started", "progress"], [call for call, _ in sink.timeouts])
        self.assertTrue(all(0 < limit <= 0.5 for _, limit in sink.timeouts))

    def test_rejected_progress_ends_the_lease_at_that_checkpoint(self) -> None:
        for status in (401, 403, 404, 409, 410):
            with self.subTest(status=status):
                sink = _RejectingSink("progress", status)
                runner = self._lease_runner(
                    sink, _LeaseCheckExecutor(timeout_seconds=3), max_failures=100
                )

                with self.assertLogs(
                    "testing_agent_ai_worker.worker.runner", level="WARNING"
                ) as logs:
                    result = runner.process_task(self._make_task())

                self.assertIsNone(result)
                self.assertEqual([], sink.result_calls)
                output = "\n".join(logs.output)
                self.assertIn(f"progress_rejected status={status}", output)
                self.assertNotIn("SECRET-MARKER", output)

    def test_progress_request_problem_is_not_a_lost_lease(self) -> None:
        for status in (400, 422, 500):
            with self.subTest(status=status):
                sink = _RejectingSink("progress", status)
                runner = self._lease_runner(sink, _SuccessfulExecutor())

                with self.assertLogs(
                    "testing_agent_ai_worker.worker.runner", level="WARNING"
                ) as logs:
                    result = runner.process_task(self._make_task())

                # The request was wrong, not the lease: the result is still delivered.
                self.assertEqual([result], sink.result_calls)
                self.assertNotIn("task lease lost", "\n".join(logs.output))

    def test_rejected_heartbeat_ends_the_lease_before_the_failure_threshold(self) -> None:
        sink = _RejectingSink("heartbeat", 409)
        runner = self._lease_runner(sink, _LeaseCheckExecutor(timeout_seconds=3), max_failures=100)

        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
            result = runner.process_task(self._make_task())

        self.assertIsNone(result)
        self.assertEqual([], sink.result_calls)
        self.assertIn("heartbeat_rejected status=409", "\n".join(logs.output))

    def test_rejected_start_runs_nothing_and_reports_nothing(self) -> None:
        sink = _RejectingSink("started", 409)
        runner = self._lease_runner(sink, _SuccessfulExecutor())

        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
            result = runner.process_task(self._make_task())

        self.assertIsNone(result)
        self.assertEqual([], sink.heartbeat_calls)
        self.assertEqual([], sink.progress_calls)
        self.assertEqual([], sink.result_calls)
        self.assertIn("start_rejected status=409", "\n".join(logs.output))

    def test_a_heartbeat_answer_that_outlives_its_window_does_not_revive_the_lease(self) -> None:
        # Sent at 0.2s into a one-second lease and answered at 1.7s: the window it
        # was meant to extend has already passed. No progress renews it meanwhile.
        sink = _SlowAnswerHeartbeatSink(delay=1.5)
        runner = self._lease_runner(sink, _SleepingExecutor(2.0), interval=0.2, max_failures=100)

        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
            result = runner.process_task(self._make_task())

        self.assertIsNone(result)
        self.assertEqual([], sink.result_calls)
        self.assertIn("late_heartbeat", "\n".join(logs.output))

    def test_a_started_answer_that_outlives_its_window_does_not_start_execution(self) -> None:
        # Sent at 0s into a one-second lease and answered at 1.5s.
        sink = _SlowAnswerStartSink(delay=1.5)
        runner = self._lease_runner(sink, _SuccessfulExecutor(), max_failures=100)

        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
            result = runner.process_task(self._make_task())

        self.assertIsNone(result)
        self.assertEqual([], sink.heartbeat_calls)
        self.assertEqual([], sink.progress_calls)
        self.assertEqual([], sink.result_calls)
        self.assertIn("late_start", "\n".join(logs.output))

    def test_a_progress_answer_that_outlives_the_window_stops_at_that_checkpoint(self) -> None:
        # Heartbeats are held so only the progress call can renew the lease.
        sink = _SlowProgressHangingHeartbeatSink(delay=1.5)
        runner = self._lease_runner(sink, _SuccessfulExecutor(), max_failures=100)

        try:
            with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
                result = runner.process_task(self._make_task())
        finally:
            sink.release.set()

        self.assertIsNone(result)
        self.assertEqual([], sink.result_calls)
        self.assertIn("late_progress", "\n".join(logs.output))

    def test_a_stale_progress_answer_does_not_end_a_window_renewed_by_heartbeat(self) -> None:
        # The progress call was sent before the last heartbeat; its late answer
        # must not shorten the newer window.
        sink = _SlowAnswerProgressSink(delay=1.5)
        runner = self._lease_runner(sink, _SuccessfulExecutor(), interval=0.2, max_failures=100)

        result = runner.process_task(self._make_task())

        self.assertIsNotNone(result)
        self.assertEqual([result], sink.result_calls)

    def test_result_submission_failure_is_preserved_and_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sink = _FlakyResultSink()
            outbox = ResultOutbox(temp_dir)
            runner = WorkerRunner(
                executor=_SuccessfulExecutor(),
                result_sink=sink,
                lifecycle=lifecycle(),
                outbox=outbox,
            )

            with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
                result = runner.process_task(self._make_task())

            self.assertIsNotNone(result)
            self.assertEqual([], sink.result_calls)
            entries = list(Path(temp_dir).glob("*.json"))
            self.assertEqual(1, len(entries))
            output = "\n".join(logs.output)
            self.assertIn("task result saved to outbox", output)
            self.assertNotIn("SECRET-MARKER", output)

            sink.fail_next = False
            outcome = runner.recover_outbox()

            self.assertIsNotNone(outcome)
            self.assertEqual(1, outcome.delivered)
            self.assertEqual([result], sink.result_calls)
            self.assertEqual([], list(Path(temp_dir).glob("*.json")))


class WorkerLifecycleTests(unittest.TestCase):
    def test_heartbeat_interval_is_at_most_half_the_lease(self) -> None:
        lifecycle = WorkerLifecycle(
            poll_interval_seconds=10, heartbeat_interval_seconds=15, run_once=False
        )

        self.assertEqual(15, lifecycle.heartbeat_interval_for(30))
        self.assertEqual(5, lifecycle.heartbeat_interval_for(10))
        self.assertEqual(1, lifecycle.heartbeat_interval_for(1))

    def test_heartbeat_interval_without_a_configured_value_is_half_the_lease(self) -> None:
        lifecycle = WorkerLifecycle(
            poll_interval_seconds=10, heartbeat_interval_seconds=0, run_once=False
        )

        self.assertEqual(15, lifecycle.heartbeat_interval_for(30))
        self.assertEqual(1, lifecycle.heartbeat_interval_for(2))


if __name__ == "__main__":
    unittest.main()
