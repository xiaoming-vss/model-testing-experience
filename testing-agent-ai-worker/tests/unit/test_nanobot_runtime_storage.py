import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nanobot import Nanobot
from pydantic import ValidationError

from testing_agent_ai_worker.config.models import NanobotConfig
from testing_agent_ai_worker.models.task import LlmCredentials, Task, TaskPayload
from testing_agent_ai_worker.nanobot_runtime import config_builder
from testing_agent_ai_worker.nanobot_runtime.paths import migrate_legacy_sessions


class NanobotRuntimeStorageTests(unittest.TestCase):
    def test_sdk_reopens_session_after_task_config_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "runtime"
            workspace = root / "workspaces" / "project-test"
            template = Path(directory) / "template.json"
            template.write_text(json.dumps({"agents": {"defaults": {"provider": "custom"}}}))
            settings = NanobotConfig(runtime_root=str(root))
            task = Task(
                task_id="storage-test",
                run_id="run-test",
                generate_task_id="generate-test",
                task_type="functional_case_generate",
                payload=TaskPayload(
                    openapi_content="",
                    llm_credentials=LlmCredentials(
                        model="test-model",
                        api_key="test-key",
                        base_url="https://example.test/v1",
                    ),
                ),
            )
            with patch.object(config_builder, "DEFAULT_TEMPLATE_PATH", template):
                with config_builder.task_config_path(nanobot_config=settings, task=task) as first:
                    bot = Nanobot.from_config(config_path=first, workspace=workspace)
                    manager = bot._loop.sessions
                    self.assertEqual(manager.sessions_dir.parent, root / "sessions")
                    session = manager.get_or_create("persistent-test")
                    session.add_message("user", "preserved across task configurations")
                    manager.save(session)
                self.assertFalse(Path(first).exists())
                with config_builder.task_config_path(nanobot_config=settings, task=task) as second:
                    self.assertNotEqual(first, second)
                    bot = Nanobot.from_config(config_path=second, workspace=workspace)
                    session = bot._loop.sessions.get_or_create("persistent-test")
                    self.assertEqual(
                        session.messages[-1]["content"], "preserved across task configurations"
                    )
                self.assertFalse(Path(second).exists())

    def test_legacy_sessions_move_once_without_changing_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "temp-configs" / "sessions"
            (old / "workspace-id").mkdir(parents=True)
            (old / "workspace-id/session.jsonl").write_text("history")
            settings = NanobotConfig(runtime_root=str(root))
            migrate_legacy_sessions(settings)
            migrate_legacy_sessions(settings)
            self.assertFalse(old.exists())
            self.assertEqual((root / "sessions/workspace-id/session.jsonl").read_text(), "history")

    def test_migration_conflict_preserves_both_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "temp-configs" / "sessions"
            old.mkdir(parents=True)
            (old / "session.jsonl").write_text("old")
            (root / "sessions").mkdir()
            (root / "sessions/session.jsonl").write_text("new")
            with self.assertRaisesRegex(RuntimeError, "会话迁移冲突"):
                migrate_legacy_sessions(NanobotConfig(runtime_root=str(root)))
            self.assertEqual((old / "session.jsonl").read_text(), "old")
            self.assertEqual((root / "sessions/session.jsonl").read_text(), "new")

    def test_stream_idle_timeout_must_be_positive_and_finite(self):
        self.assertEqual(NanobotConfig().stream_idle_timeout_seconds, 300)
        for value in (0, -1, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                NanobotConfig(stream_idle_timeout_seconds=value)
