import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DbSessionConfigTests(unittest.TestCase):
    def _import_session(self, config_text: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "control-plane.toml"
            config.write_text(config_text, encoding="utf-8")
            env = os.environ.copy()
            env["APP_CONF"] = str(config)
            return subprocess.run(
                [sys.executable, "-c", "import testing_agent.db.session"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )

    def test_empty_dsn_fails_fast(self):
        result = self._import_session("")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data.db.user.dsn", result.stderr)

    def test_valid_dsn_imports(self):
        result = self._import_session('[data.db.user]\ndsn = "sqlite+aiosqlite:///:memory:"\n')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
