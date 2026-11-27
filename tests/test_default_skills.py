import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "apps/control-plane/default-skills"


class DefaultSkillTests(unittest.TestCase):
    def test_every_bundled_skill_test_suite_passes(self) -> None:
        suites = sorted((SKILLS / name / "tests", name) for name in os.listdir(SKILLS))
        suites = [(path, name) for path, name in suites if path.is_dir()]
        self.assertTrue(suites)
        for path, name in suites:
            with self.subTest(skill=name):
                result = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
                    cwd=path.parent,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
