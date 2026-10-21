import json
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker_pi.config.models import PiConfig
from testing_agent_ai_worker_pi.models.task import LlmCredentials, Task, TaskPayload
from testing_agent_ai_worker_pi.pi_runtime.client import Pi
from testing_agent_ai_worker_pi.pi_runtime.config_builder import (
    cleanup_task_configs,
    task_config_path,
)


class PiConfigTests(unittest.TestCase):
    def test_private_credentials_and_cleanup_on_failure(self):
        with tempfile.TemporaryDirectory() as root:
            task = Task(
                task_id="a",
                run_id="b",
                generate_task_id="c",
                task_type="api_case_generate",
                payload=TaskPayload(
                    openapi_content="",
                    llm_credentials=LlmCredentials(
                        model="m", api_key="secret", base_url="https://example.test/v1"
                    ),
                ),
            )
            with self.assertRaisesRegex(RuntimeError, "test"):
                with task_config_path(pi_config=PiConfig(runtime_root=root), task=task) as name:
                    p = Path(name)
                    self.assertEqual(p.stat().st_mode & 0o777, 0o600)
                    data = json.loads(p.read_text())
                    self.assertEqual(data["api_key"], "secret")
                    self.assertEqual(data["model"], "m")
                    self.assertEqual(data["executable"], "pi")
                    cleanup_task_configs()
                    self.assertFalse(p.exists())
                    raise RuntimeError("test")
            self.assertFalse(p.exists())

    def test_missing_credentials_cannot_start_pi(self):
        with tempfile.TemporaryDirectory() as root:
            task = Task(
                task_id="a",
                run_id="b",
                generate_task_id="c",
                task_type="api_case_generate",
                payload=TaskPayload(openapi_content=""),
            )
            with task_config_path(pi_config=PiConfig(runtime_root=root), task=task) as name:
                with self.assertRaisesRegex(ValueError, "credentials"):
                    Pi.from_config(config_path=name, workspace=root)
