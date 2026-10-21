import tomllib
import unittest
from pathlib import Path


class ProjectMetadataTests(unittest.TestCase):
    def test_independent_python_entrypoint_without_nanobot_dependency(self):
        data = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())
        self.assertEqual(data["project"]["name"], "mtx-ai-worker-pi")
        self.assertEqual(
            data["project"]["scripts"], {"mtx-ai-worker-pi": "testing_agent_ai_worker_pi.main:main"}
        )
        self.assertFalse(any("nanobot" in d for d in data["project"]["dependencies"]))
