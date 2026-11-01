"""Contract tests for backend selection and shared agent wiring."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from testing_agent_ai_worker.agent import (
    apply_environment,
    create_agent,
    resolve_runtime_paths,
    task_config_path,
    verify_runtime,
)
from testing_agent_ai_worker.agent.base import AgentConfigPath
from testing_agent_ai_worker.config.models import AgentConfig, NanobotConfig, PiConfig
from testing_agent_ai_worker.models.task import LlmCredentials, Task, TaskPayload


class AgentSelectionTests(unittest.TestCase):
    def test_agent_config_selects_active_backend(self) -> None:
        nanobot = AgentConfig(backend="nanobot")
        pi = AgentConfig(backend="pi")

        self.assertIsInstance(nanobot.active, NanobotConfig)
        self.assertIsInstance(pi.active, PiConfig)
        self.assertEqual(pi.active.backend, "pi")

    def test_create_agent_dispatches_on_config_path_backend(self) -> None:
        sentinel = object()
        with (
            patch(
                "testing_agent_ai_worker.agent.pi.Pi.from_config",
                return_value=sentinel,
            ) as pi_factory,
            patch(
                "testing_agent_ai_worker.agent.nanobot.NanobotAgent.from_config",
                return_value=sentinel,
            ) as nanobot_factory,
        ):
            self.assertIs(
                create_agent(config_path=AgentConfigPath("task.json", "pi"), workspace="work"),
                sentinel,
            )
            pi_factory.assert_called_once_with(config_path="task.json", workspace="work")
            self.assertIs(create_agent(config_path="task.json", workspace="work"), sentinel)
            nanobot_factory.assert_called_once_with(config_path="task.json", workspace="work")

    def test_explicit_backend_overrides_plain_config_path(self) -> None:
        sentinel = object()
        with patch(
            "testing_agent_ai_worker.agent.pi.Pi.from_config", return_value=sentinel
        ) as pi_factory:
            self.assertIs(
                create_agent(config_path="task.json", workspace="work", backend="pi"),
                sentinel,
            )
        pi_factory.assert_called_once_with(config_path="task.json", workspace="work")

    def test_create_agent_rejects_unknown_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported agent backend"):
            create_agent(config_path="task.json", backend="typo")

    def test_runtime_paths_use_the_selected_backend_root(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = resolve_runtime_paths(PiConfig(runtime_root=root))

            self.assertEqual(paths.runtime_root, Path(root).resolve())
            self.assertEqual(paths.workspaces_dir, Path(root).resolve() / "workspaces")

    def test_apply_environment_only_configures_nanobot(self) -> None:
        keys = ("NANOBOT_STREAM_IDLE_TIMEOUT_S", "NANOBOT_OPENAI_COMPAT_TIMEOUT_S")
        with patch.dict(os.environ, {}, clear=False):
            for key in keys:
                os.environ.pop(key, None)
            apply_environment(
                NanobotConfig(
                    stream_idle_timeout_seconds=240,
                    provider_request_timeout_seconds=300,
                )
            )
            self.assertEqual(os.environ[keys[0]], "240")
            self.assertEqual(os.environ[keys[1]], "300")

            for key in keys:
                os.environ.pop(key, None)
            apply_environment(PiConfig())
            self.assertNotIn(keys[0], os.environ)
            self.assertNotIn(keys[1], os.environ)

    def test_verify_runtime_checks_pi_but_not_nanobot(self) -> None:
        with patch("testing_agent_ai_worker.agent.check_runtime") as check:
            verify_runtime(NanobotConfig())
            check.assert_not_called()
            verify_runtime(PiConfig(executable="pi-test"))
            check.assert_called_once_with("pi-test")


class TaskConfigPathTests(unittest.TestCase):
    def _task(self) -> Task:
        return Task(
            task_id="task-1",
            run_id="run-1",
            generate_task_id="generate-1",
            task_type="api_case_generate",
            payload=TaskPayload(
                openapi_content="{}",
                llm_credentials=LlmCredentials(
                    model="gpt-test", api_key="secret", base_url="https://example.test/v1"
                ),
            ),
        )

    def test_pi_config_is_private_and_removed_after_use(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with task_config_path(
                agent_config=PiConfig(runtime_root=root), task=self._task()
            ) as config_path:
                self.assertIsInstance(config_path, AgentConfigPath)
                self.assertEqual(config_path.backend, "pi")
                path = Path(config_path)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["api_key"], "secret")
                self.assertEqual(payload["model"], "gpt-test")
                self.assertNotIn("backend", payload)
            self.assertFalse(Path(config_path).exists())

    def test_nanobot_config_keeps_sdk_schema_and_is_removed_after_use(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            template = Path(root) / "nanobot.template.json"
            template.write_text("{}", encoding="utf-8")
            with patch("testing_agent_ai_worker.agent.nanobot.DEFAULT_TEMPLATE_PATH", template):
                with task_config_path(
                    agent_config=NanobotConfig(runtime_root=root), task=self._task()
                ) as config_path:
                    self.assertIsInstance(config_path, AgentConfigPath)
                    self.assertEqual(config_path.backend, "nanobot")
                    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
                    self.assertNotIn("backend", payload)
                    self.assertEqual(payload["providers"]["custom"]["apiKey"], "secret")
                self.assertFalse(Path(config_path).exists())


if __name__ == "__main__":
    unittest.main()
