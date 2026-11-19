from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_k8s_config.py"

PLATFORM_TOML = """
[shared]
worker_token = "worker-token-000000000000000000"
integration_worker_token = "integration-token-000000000000"
jwt_key = "jwt-key-0000000000000000000000"
integration_key = "integration-key-00000000000000"
integration_runtime_generation = "runtime-generation-000000000"

[database]
url = "mysql+asyncmy://user:pass@db.internal:3306/mtx"

[redis]
url = "redis://redis.internal:6379/0"

[control_plane.security.super_admin]
username = "admin"
email = "admin@example.com"
initial_password = "initial-password-000000000000"

[control_plane.integration_execution]
enabled = false

[control_plane.storage.s3]
enabled = false

[ai_worker.agent]
backend = "nanobot"
"""

CONTROL_PLANE_VALUES = """
config:
  security:
    jwt:
      key: "jwt-key-0000000000000000000000"
    worker:
      key: "worker-token-000000000000000000"
    integration:
      key: "integration-key-00000000000000"
    integration_worker:
      key: "integration-token-000000000000"
    super_admin:
      username: "admin"
      email: "admin@example.com"
      initial_password: "initial-password-000000000000"
  integration_execution:
    enabled: false
  data:
    db:
      user:
        dsn: "mysql+asyncmy://user:pass@db.internal:3306/mtx"
  test_run_notifications:
    redis_url: "redis://redis.internal:6379/0"
  storage:
    s3:
      enabled: false
"""

AI_WORKER_VALUES = """
config:
  platform:
    worker_token: "worker-token-000000000000000000"
  agent:
    backend: "nanobot"
"""

API_UI_WORKER_VALUES = """
config:
  control_plane:
    worker_token: "worker-token-000000000000000000"
  notifications:
    redis_url: "redis://redis.internal:6379/0"
"""

INTEGRATION_WORKER_VALUES = """
config:
  control_plane:
    worker_token: "integration-token-000000000000"
"""


class K8sConfigCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.platform = self.root / "platform.toml"
        self.platform.write_text(PLATFORM_TOML, encoding="utf-8")
        self.values = self.root / "values"
        self.values.mkdir()
        self.write_values()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_values(self, **overrides: str) -> None:
        files = {
            "control-plane-values.yaml": CONTROL_PLANE_VALUES,
            "ai-worker-values.yaml": AI_WORKER_VALUES,
            "api-ui-worker-values.yaml": API_UI_WORKER_VALUES,
            "integration-worker-values.yaml": INTEGRATION_WORKER_VALUES,
        }
        files.update(overrides)
        for name, content in files.items():
            (self.values / name).write_text(content, encoding="utf-8")

    def run_check(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--platform-config",
                str(self.platform),
                "--values-dir",
                str(self.values),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_matching_values_pass(self) -> None:
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 failure(s)", result.stdout)

    def test_template_defaults_pass(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 failure(s)", result.stdout)

    def test_database_drift_fails(self) -> None:
        self.write_values(
            **{
                "control-plane-values.yaml": CONTROL_PLANE_VALUES.replace(
                    "db.internal:3306/mtx", "db.other:3306/mtx"
                )
            }
        )
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Database", result.stdout)

    def test_redis_drift_fails(self) -> None:
        self.write_values(
            **{
                "api-ui-worker-values.yaml": API_UI_WORKER_VALUES.replace(
                    "redis.internal:6379/0", "redis.other:6379/0"
                )
            }
        )
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Redis", result.stdout)

    def test_s3_enabled_drift_fails(self) -> None:
        self.write_values(
            **{
                "control-plane-values.yaml": CONTROL_PLANE_VALUES.replace(
                    "s3:\n      enabled: false", "s3:\n      enabled: true"
                )
            }
        )
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("S3", result.stdout)

    def test_worker_token_drift_fails_without_printing_secret(self) -> None:
        token = "worker-token-000000000000000000"
        self.write_values(
            **{
                "ai-worker-values.yaml": AI_WORKER_VALUES.replace(
                    token, "worker-token-different-00000000"
                )
            }
        )
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Worker token", result.stdout)
        self.assertNotIn(token, result.stdout)
        self.assertNotIn(token, result.stderr)

    def test_agent_backend_drift_fails(self) -> None:
        self.write_values(
            **{
                "ai-worker-values.yaml": AI_WORKER_VALUES.replace(
                    "backend: \"nanobot\"", "backend: \"pi\""
                )
            }
        )
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("AI backend", result.stdout)


if __name__ == "__main__":
    unittest.main()
