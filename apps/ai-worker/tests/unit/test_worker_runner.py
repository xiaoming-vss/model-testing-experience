import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.platform.result_sink import ResultSink
from testing_agent_ai_worker.services.result_service import ResultService
from testing_agent_ai_worker.worker.lifecycle import WorkerLifecycle
from testing_agent_ai_worker.worker.outbox import ResultOutbox
from testing_agent_ai_worker.worker.runner import LeaseLostError, TaskExecutor, WorkerRunner


class _RecordingSink(ResultSink):
    def __init__(self) -> None:
        self.started_calls: list[tuple[str, str, str]] = []
        self.heartbeat_calls: list[tuple[str, str, str]] = []
        self.progress_calls: list[TaskProgress] = []
        self.result_calls: list[TaskResult] = []
        self.first_heartbeat = threading.Event()

    def mark_started(self, task_id: str, attempt_id: str, started_at_iso: str) -> None:
        self.started_calls.append((task_id, attempt_id, started_at_iso))

    def send_heartbeat(self, task_id: str, attempt_id: str, heartbeat_at_iso: str) -> None:
        self.heartbeat_calls.append((task_id, attempt_id, heartbeat_at_iso))
        self.first_heartbeat.set()

    def submit_progress(self, progress: TaskProgress) -> None:
        self.progress_calls.append(progress)

    def submit_result(self, result: TaskResult) -> None:
        self.result_calls.append(result)


class _FailingProgressSink(_RecordingSink):
    def submit_progress(self, progress: TaskProgress) -> None:
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
    def send_heartbeat(self, task_id: str, attempt_id: str, heartbeat_at_iso: str) -> None:
        raise RuntimeError("SECRET-MARKER heartbeat endpoint unavailable")


class _FailingProgressAndHeartbeatSink(_FailingHeartbeatSink):
    def submit_progress(self, progress: TaskProgress) -> None:
        raise RuntimeError("progress endpoint unavailable")


class _FlakyHeartbeatSink(_RecordingSink):
    def __init__(self, *, failures_before_success: int) -> None:
        super().__init__()
        self.failures_before_success = failures_before_success
        self.attempts = 0

    def send_heartbeat(self, task_id: str, attempt_id: str, heartbeat_at_iso: str) -> None:
        self.attempts += 1
        if self.attempts <= self.failures_before_success:
            raise RuntimeError("heartbeat endpoint unavailable")
        super().send_heartbeat(task_id, attempt_id, heartbeat_at_iso)


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
                output_yaml='{"cases":[]}',
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
                output_yaml='{"cases":[]}',
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
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=60,
                run_once=False,
            ),
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
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=60,
                run_once=False,
            ),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(1, len(sink.result_calls))
        self.assertEqual(TaskStatus.SUCCESS, sink.result_calls[0].status)

    def test_process_task_logs_result_submission_failure_without_raising(self) -> None:
        sink = _FailingResultSink()
        runner = WorkerRunner(
            executor=_SuccessfulExecutor(),
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=60,
                run_once=False,
            ),
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
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=1,
                run_once=False,
            ),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertGreaterEqual(len(sink.heartbeat_calls), 1)

    def test_process_task_turns_executor_error_into_final_error_result(self) -> None:
        sink = _RecordingSink()
        runner = WorkerRunner(
            executor=_ExplodingExecutor(),
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=60,
                run_once=False,
            ),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(result.status, TaskStatus.ERROR)
        self.assertEqual(result.error_message, "RuntimeError: 任务执行失败，请查看 Worker 日志")
        self.assertEqual(result.intermediate_json_text, '{"enhancedText":"snapshot text"}')
        self.assertEqual(sink.result_calls[0].status, TaskStatus.ERROR)
        self.assertEqual(
            sink.result_calls[0].intermediate_json_text, '{"enhancedText":"snapshot text"}'
        )

    def test_executor_error_log_and_result_omit_provider_message(self) -> None:
        class SecretExecutor(TaskExecutor):
            def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
                raise RuntimeError("SECRET-MARKER prompt and token")

        runner = WorkerRunner(
            executor=SecretExecutor(),
            result_service=ResultService(_RecordingSink()),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=60,
                run_once=False,
            ),
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
            result_service=ResultService(_RecordingSink()),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=60,
                run_once=False,
            ),
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
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=60,
                run_once=False,
            ),
        )

        result = runner.process_task(self._make_task())

        self.assertEqual(result.status, TaskStatus.ERROR)
        self.assertEqual(result.error_message, "RuntimeError: 任务执行失败，请查看 Worker 日志")
        self.assertEqual(
            result.intermediate_json_text, '{"enhancedText":"progress text","caseNames":[]}'
        )
        self.assertEqual(result.output_yaml, '{"cases":[]}')
        self.assertEqual(result.result_summary_json, '{"status":"running","stage":"case_names"}')

    def test_process_task_submits_failed_result_when_credentials_are_missing(self) -> None:
        sink = _RecordingSink()
        task = self._make_task()
        task.credential_error = "credentials unavailable"
        runner = WorkerRunner(
            executor=_ExplodingExecutor(),
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=60,
                run_once=False,
            ),
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
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=60,
                run_once=False,
            ),
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
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=0.01,
                run_once=False,
            ),
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
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=0.05,
                run_once=False,
            ),
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
            result_service=ResultService(sink),
            lifecycle=WorkerLifecycle(
                poll_interval_seconds=10,
                heartbeat_interval_seconds=0.01,
                run_once=False,
            ),
            heartbeat_max_failures=3,
        )

        with self.assertLogs("testing_agent_ai_worker.worker.runner", level="WARNING") as logs:
            result = runner.process_task(self._make_task())

        self.assertIsNotNone(result)
        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertGreaterEqual(sink.attempts, 3)
        self.assertEqual(1, len(sink.result_calls))
        self.assertNotIn("task lease lost", "\n".join(logs.output))

    def test_result_submission_failure_is_preserved_and_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sink = _FlakyResultSink()
            outbox = ResultOutbox(temp_dir)
            runner = WorkerRunner(
                executor=_SuccessfulExecutor(),
                result_service=ResultService(sink),
                lifecycle=WorkerLifecycle(
                    poll_interval_seconds=10,
                    heartbeat_interval_seconds=60,
                    run_once=False,
                ),
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


if __name__ == "__main__":
    unittest.main()
