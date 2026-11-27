import json
import os
import stat
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from testing_agent_ai_worker.models.execution import TaskResult, TaskStatus
from testing_agent_ai_worker.worker.outbox import ResultOutbox


def _result(task_id: str = "task-1", *, output: str = "result-yaml") -> TaskResult:
    now = datetime.now(UTC)
    return TaskResult(
        task_id=task_id,
        attempt_id="run-1",
        generate_task_id="generate-1",
        status=TaskStatus.SUCCESS,
        output_yaml=output,
        started_at=now,
        finished_at=now,
    )


class ResultOutboxTests(unittest.TestCase):
    def test_save_writes_owner_only_entry_and_drain_delivers_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = ResultOutbox(temp_dir)
            result = _result()
            path = outbox.save(
                result,
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
            )

            self.assertTrue(path.is_file())
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(1, payload["version"])
            self.assertEqual("result-yaml", payload["result"]["output_yaml"])

            delivered: list[TaskResult] = []
            outcome = outbox.drain(delivered.append)

            self.assertEqual(1, outcome.delivered)
            self.assertEqual(0, outcome.failed)
            self.assertEqual(0, outcome.expired)
            self.assertEqual([result], delivered)
            self.assertFalse(path.exists())

    def test_expired_entry_is_retained_but_not_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = ResultOutbox(temp_dir)
            path = outbox.save(
                _result(),
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )

            delivered: list[TaskResult] = []
            outcome = outbox.drain(delivered.append)

            self.assertEqual(0, outcome.delivered)
            self.assertEqual(1, outcome.expired)
            self.assertEqual([], delivered)
            self.assertTrue(path.exists())

    def test_failed_submission_keeps_entry_for_next_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = ResultOutbox(temp_dir)
            path = outbox.save(
                _result(),
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
            )

            def fail_submit(_result: TaskResult) -> None:
                raise RuntimeError("SECRET-MARKER delivery failed")

            outcome = outbox.drain(fail_submit)

            self.assertEqual(0, outcome.delivered)
            self.assertEqual(1, outcome.failed)
            self.assertTrue(path.exists())

    def test_corrupt_entry_is_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = ResultOutbox(temp_dir)
            path = Path(temp_dir) / "corrupt.json"
            path.write_text("{not-json", encoding="utf-8")

            outcome = outbox.drain(lambda _result: None)

            self.assertEqual(1, outcome.discarded)
            self.assertFalse(path.exists())

    def test_retention_prunes_old_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = ResultOutbox(temp_dir, retention_seconds=60)
            path = outbox.save(
                _result(),
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
            old = datetime.now(UTC).timestamp() - 3600
            os.utime(path, (old, old))

            outcome = outbox.drain(lambda _result: None)

            self.assertEqual(1, outcome.expired)
            self.assertEqual(1, outcome.discarded)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
