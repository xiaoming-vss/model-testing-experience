import os
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from testing_agent_ai_worker.app.health import (
    HealthServer,
    health_port_from_env,
)


class HealthServerTests(unittest.TestCase):
    def _start_server(self) -> HealthServer:
        server = HealthServer(host="127.0.0.1", port=0)
        server.start()
        self.addCleanup(server.stop)
        return server

    def test_healthz_returns_ok(self) -> None:
        server = self._start_server()

        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/healthz",
            timeout=2,
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"ok\n")

    def test_unknown_path_returns_404(self) -> None:
        server = self._start_server()

        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.port}/unknown",
                timeout=2,
            )

        self.assertEqual(caught.exception.code, 404)

    def test_unset_port_env_disables_health_server(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(health_port_from_env())

    def test_invalid_port_env_falls_back_to_default(self) -> None:
        with patch.dict(os.environ, {"TESTING_AGENT_HEALTH_PORT": "not-a-port"}):
            self.assertEqual(health_port_from_env(), 8080)


if __name__ == "__main__":
    unittest.main()
