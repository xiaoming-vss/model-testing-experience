from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable


class ConfigTomlTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_cwd = Path.cwd()
        self._old_env = os.environ.copy()
        for key in list(os.environ):
            if key.startswith("TEST_WORKER_") or key.startswith("UI_WORKER_"):
                os.environ.pop(key)
        sys.modules.pop("test_worker.core.config", None)

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        os.environ.clear()
        os.environ.update(self._old_env)
        sys.modules.pop("test_worker.core.config", None)

    def _with_config_toml(self, content: str, callback: Callable[[], object]) -> object:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "config.toml").write_text(content.strip(), encoding="utf-8")
            os.chdir(tmp)
            try:
                return callback()
            finally:
                os.chdir(self._old_cwd)

    def test_load_config_reads_config_toml(self) -> None:
        config = self._with_config_toml(
            """
mode = "poll"

[control_plane]
base_url = "http://127.0.0.1:8000"
worker_token = "secret-token"

[worker]
id = "worker-a"
poll_interval_ms = 1234
request_timeout_ms = 5678
heartbeat_interval_ms = 9012

[ui]
artifacts_dir = "./tmp-artifacts"
artifacts_bind_host = "127.0.0.1"
artifacts_port = 9020
artifacts_base_url = "http://worker-a:9020"
headless = false
slow_mo_ms = 25
trace_enabled = false
screenshot_on_failure = false

[once]
snapshot_file = "./snapshot.json"
""",
            lambda: importlib.import_module("test_worker.core.config").load_config(),
        )

        self.assertEqual(config.mode, "poll")
        self.assertEqual(config.worker_id, "worker-a")
        self.assertEqual(config.control_plane_base_url, "http://127.0.0.1:8000")
        self.assertEqual(config.worker_token, "secret-token")
        self.assertEqual(config.poll_interval_ms, 1234)
        self.assertEqual(config.request_timeout_ms, 5678)
        self.assertEqual(config.heartbeat_interval_ms, 9012)
        self.assertTrue(config.artifacts_root_dir.endswith("tmp-artifacts"))
        self.assertEqual(config.artifacts_bind_host, "127.0.0.1")
        self.assertEqual(config.artifacts_port, 9020)
        self.assertEqual(config.artifacts_base_url, "http://worker-a:9020")
        self.assertFalse(config.default_headless)
        self.assertEqual(config.default_slow_mo_ms, 25)
        self.assertFalse(config.trace_enabled)
        self.assertFalse(config.screenshot_on_failure)
        self.assertEqual(config.snapshot_file, "./snapshot.json")

    def test_environment_variables_do_not_override_config_toml(self) -> None:
        os.environ["TEST_WORKER_MODE"] = "once"
        os.environ["TEST_WORKER_CONTROL_PLANE_BASE_URL"] = "http://from-env"
        os.environ["TEST_WORKER_TOKEN"] = "env-token"

        config = self._with_config_toml(
            """
mode = "poll"

[control_plane]
base_url = "http://from-toml"
worker_token = "toml-token"
""",
            lambda: importlib.import_module("test_worker.core.config").load_config(),
        )

        self.assertEqual(config.mode, "poll")
        self.assertEqual(config.control_plane_base_url, "http://from-toml")
        self.assertEqual(config.worker_token, "toml-token")


if __name__ == "__main__":
    unittest.main()
