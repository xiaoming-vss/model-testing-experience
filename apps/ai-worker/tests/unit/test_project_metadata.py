"""Project metadata and public import naming tests."""

import json
import tomllib
import unittest
from pathlib import Path


class ProjectMetadataTests(unittest.TestCase):
    def test_project_uses_mtx_name_and_keeps_legacy_entrypoints(self) -> None:
        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        metadata = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        scripts = metadata["project"]["scripts"]

        self.assertEqual(metadata["project"]["name"], "mtx-ai-worker")
        self.assertEqual(scripts["mtx-ai-worker"], "testing_agent_ai_worker.main:main")
        self.assertEqual(scripts["mtx-ai-demo"], "testing_agent_ai_worker.cli.agent_demo:main")
        self.assertEqual(
            scripts["mtx-ai-chain-demo"],
            "testing_agent_ai_worker.cli.agent_chain_demo:main",
        )
        for suffix in ("ai-worker", "ai-demo", "ai-chain-demo"):
            self.assertEqual(scripts[f"mtx-{suffix}"], scripts[f"testing-agent-{suffix}"])
        self.assertNotIn("testing-agent-worker", scripts)
        self.assertNotIn("nanobot-worker", scripts)

    def test_pi_runtime_is_pinned_as_node_dependency(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        package = json.loads((project_root / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(package["dependencies"]["@earendil-works/pi-coding-agent"], "1.3.0")
