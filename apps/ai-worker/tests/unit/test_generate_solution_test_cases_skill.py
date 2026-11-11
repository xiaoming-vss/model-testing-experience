import os
import unittest
from pathlib import Path

SKILL_ROOT = Path(
    os.environ.get(
        "DEFAULT_SKILL_SOURCE",
        Path(__file__).resolve().parents[3] / "control-plane" / "default-skills",
    )
)
SKILL_PATH = SKILL_ROOT / "generate-solution-test-cases" / "SKILL.md"


@unittest.skipUnless(SKILL_PATH.is_file(), "默认 Skill 源目录未挂载")
class GenerateSolutionTestCasesSkillTests(unittest.TestCase):
    def test_skill_requires_confirmation_answers_to_update_and_close_questions(self):
        content = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("确认承接必须闭环", content)
        self.assertIn("从 `questions`/`openQuestions` 删除已解决问题", content)
        self.assertIn("清理所有 `relatedQuestionIds`", content)
        self.assertIn("已确认的行为不能再次拆成同义或更细粒度的问题", content)


if __name__ == "__main__":
    unittest.main()
