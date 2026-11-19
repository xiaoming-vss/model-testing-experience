import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "apps/api-ui-worker"


class ApiUiDependencyTests(unittest.TestCase):
    def test_requirements_txt_matches_pyproject_dependencies(self):
        project = tomllib.loads(
            (PROJECT / "pyproject.toml").read_text(encoding="utf-8")
        )
        declared = {item.strip() for item in project["project"]["dependencies"]}
        requirements = {
            line.strip()
            for line in (PROJECT / "requirements.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertEqual(requirements, declared)


if __name__ == "__main__":
    unittest.main()
