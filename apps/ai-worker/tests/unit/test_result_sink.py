import json
import unittest
from datetime import datetime
from typing import Any

from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.platform.result_sink import HttpResultSink


class _FakePlatformClient:
    def __init__(self) -> None:
        self.post_calls: list[dict[str, Any]] = []
        self.patch_calls: list[dict[str, Any]] = []
        self.timeouts: list[tuple[str, float | None]] = []

    def post(
        self, path: str, json_body: dict[str, Any], *, timeout_seconds: float | None = None
    ) -> None:
        self.post_calls.append({"path": path, "json_body": json_body})
        self.timeouts.append((path, timeout_seconds))

    def patch(
        self, path: str, json_body: dict[str, Any], *, timeout_seconds: float | None = None
    ) -> None:
        self.patch_calls.append({"path": path, "json_body": json_body})
        self.timeouts.append((path, timeout_seconds))


class ResultSinkTests(unittest.TestCase):
    def test_http_result_sink_posts_started_and_heartbeat(self) -> None:
        client = _FakePlatformClient()
        sink = HttpResultSink(
            client=client,  # type: ignore[arg-type]
            worker_id="worker-1",
            started_path_template="/tasks/{task_id}/started",
            heartbeat_path_template="/tasks/{task_id}/heartbeat",
            progress_path_template="/tasks/{task_id}/progress",
            completed_path_template="/tasks/{task_id}/completed",
        )

        sink.mark_started("task-1", "attempt-1", "2026-06-23T10:00:00+08:00")
        sink.send_heartbeat("task-1", "attempt-1", "2026-06-23T10:00:05+08:00")

        self.assertEqual(
            client.post_calls,
            [
                {
                    "path": "/tasks/task-1/started",
                    "json_body": {
                        "workerId": "worker-1",
                        "attemptId": "attempt-1",
                        "startedAt": "2026-06-23T10:00:00+08:00",
                    },
                },
                {
                    "path": "/tasks/task-1/heartbeat",
                    "json_body": {
                        "workerId": "worker-1",
                        "attemptId": "attempt-1",
                        "heartbeatAt": "2026-06-23T10:00:05+08:00",
                    },
                },
            ],
        )

    def test_http_result_sink_patches_progress_without_completion_fields(self) -> None:
        client = _FakePlatformClient()
        sink = HttpResultSink(
            client=client,  # type: ignore[arg-type]
            worker_id="worker-1",
            started_path_template="/tasks/{task_id}/started",
            heartbeat_path_template="/tasks/{task_id}/heartbeat",
            progress_path_template="/tasks/{task_id}/progress",
            completed_path_template="/tasks/{task_id}/completed",
        )
        summary = json.dumps({"status": "running", "caseCount": 1}, ensure_ascii=False)

        sink.submit_progress(
            TaskProgress(
                task_id="task-1",
                attempt_id="run-1",
                current_stage="interface_extract",
                stage_status="running",
                intermediate_json_text='{"cases":[]}',
                result_summary_json=summary,
            )
        )

        self.assertEqual(1, len(client.patch_calls))
        progress_call = client.patch_calls[0]
        self.assertEqual("/tasks/task-1/progress", progress_call["path"])
        self.assertEqual(
            {
                "workerId": "worker-1",
                "taskId": "task-1",
                "attemptId": "run-1",
                "currentStage": "interface_extract",
                "stageStatus": "running",
                "configJson": '{"cases":[]}',
                "resultSummaryJson": summary,
            },
            progress_call["json_body"],
        )
        self.assertNotIn("status", progress_call["json_body"])
        self.assertNotIn("startedAt", progress_call["json_body"])
        self.assertNotIn("finishedAt", progress_call["json_body"])

    def test_http_result_sink_posts_completed_payload(self) -> None:
        client = _FakePlatformClient()
        sink = HttpResultSink(
            client=client,  # type: ignore[arg-type]
            worker_id="worker-1",
            started_path_template="/tasks/{task_id}/started",
            heartbeat_path_template="/tasks/{task_id}/heartbeat",
            progress_path_template="/tasks/{task_id}/progress",
            completed_path_template="/tasks/{task_id}/completed",
        )
        started_at = datetime.fromisoformat("2026-06-23T10:00:00+08:00")
        finished_at = datetime.fromisoformat("2026-06-23T10:00:08+08:00")

        sink.submit_result(
            TaskResult(
                task_id="task-1",
                attempt_id="run-1",
                generate_task_id="generate-1",
                status=TaskStatus.SUCCESS,
                intermediate_json_text='{"cases":[]}',
                output_yaml="cases: []",
                result_summary_json='{"status":"success"}',
                started_at=started_at,
                finished_at=finished_at,
            )
        )

        self.assertEqual(
            client.post_calls[0],
            {
                "path": "/tasks/task-1/completed",
                "json_body": {
                    "workerId": "worker-1",
                    "taskId": "task-1",
                    "attemptId": "run-1",
                    "status": "success",
                    "startedAt": "2026-06-23T10:00:00+08:00",
                    "finishedAt": "2026-06-23T10:00:08+08:00",
                    "errorMessage": "",
                    "configJson": '{"cases":[]}',
                    "resultYaml": "cases: []",
                    "resultSummaryJson": '{"status":"success"}',
                },
            },
        )

    def test_renewing_calls_pass_the_callers_bound_to_the_client(self) -> None:
        client = _FakePlatformClient()
        sink = HttpResultSink(
            client=client,  # type: ignore[arg-type]
            worker_id="worker-1",
            started_path_template="/tasks/{task_id}/started",
            heartbeat_path_template="/tasks/{task_id}/heartbeat",
            progress_path_template="/tasks/{task_id}/progress",
            completed_path_template="/tasks/{task_id}/completed",
        )

        sink.mark_started("task-1", "attempt-1", "2026-06-23T10:00:00+08:00", timeout_seconds=4)
        sink.send_heartbeat("task-1", "attempt-1", "2026-06-23T10:00:05+08:00", timeout_seconds=3)
        sink.submit_progress(
            TaskProgress(
                task_id="task-1", attempt_id="run-1", current_stage="s", stage_status="running"
            ),
            timeout_seconds=2,
        )
        sink.submit_result(
            TaskResult(
                task_id="task-1",
                attempt_id="run-1",
                status=TaskStatus.SUCCESS,
                started_at=datetime.fromisoformat("2026-06-23T10:00:00+08:00"),
                finished_at=datetime.fromisoformat("2026-06-23T10:00:08+08:00"),
            )
        )

        # The completion is decided when the control plane receives it; it is never cut short.
        self.assertEqual(
            [
                ("/tasks/task-1/started", 4),
                ("/tasks/task-1/heartbeat", 3),
                ("/tasks/task-1/progress", 2),
                ("/tasks/task-1/completed", None),
            ],
            client.timeouts,
        )


if __name__ == "__main__":
    unittest.main()
