"""The default UI execution capabilities of both applications mirror the skills' execution profile."""

import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = (
    ROOT
    / "apps/control-plane/default-skills/mtx-generate-ui-test-case/references/execution-profile.json"
)
CAPABILITY_SOURCES = {
    "control-plane": ROOT
    / "apps/control-plane/src/testing_agent/domain/ui_generation_artifacts.py",
    "ai-worker": ROOT
    / "apps/ai-worker/src/testing_agent_ai_worker/tasks/ui_case_generate/artifacts.py",
}


def assigned_constant(path: Path, name: str):
    """Read a module-level literal without importing the application that owns it."""
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not a literal constant in {path}")


class UiExecutionProfileTests(unittest.TestCase):
    def test_applications_mirror_the_profile_capabilities(self):
        # The two skills bundle byte-identical copies of the profile; that pair is a contract group.
        profile = json.loads(PROFILE.read_text())
        for application, path in CAPABILITY_SOURCES.items():
            with self.subTest(application=application):
                self.assertEqual(assigned_constant(path, "DEFAULT_CAPABILITIES"), profile["capabilities"])


if __name__ == "__main__":
    unittest.main()
