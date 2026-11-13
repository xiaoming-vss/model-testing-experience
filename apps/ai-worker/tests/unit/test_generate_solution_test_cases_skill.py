import os
import unittest
from pathlib import Path

SKILL_ROOT = Path(
    os.environ.get(
        "DEFAULT_SKILL_SOURCE",
        Path(__file__).resolve().parents[3] / "control-plane" / "default-skills",
    )
)
SKILL_PATH = SKILL_ROOT / "mtx-generate-solution-test-cases" / "SKILL.md"


@unittest.skipUnless(SKILL_PATH.is_file(), "默认 Skill 源目录未挂载")
class GenerateSolutionTestCasesSkillTests(unittest.TestCase):
    def test_skill_keeps_the_case_output_contract_and_clarification_protocol(self):
        content = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("name: mtx-generate-solution-test-cases", content)
        self.assertIn("顶层只有 `cases`", content)
        self.assertIn("恰好七字段", content)
        self.assertIn("CLARIFICATION_REQUIRED:", content)


if __name__ == "__main__":
    unittest.main()
