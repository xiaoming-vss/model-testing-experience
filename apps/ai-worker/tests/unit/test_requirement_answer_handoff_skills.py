import os
import unittest
from pathlib import Path

SKILL_ROOTS = [
    Path(
        os.environ.get(
            "DEFAULT_SKILL_SOURCE",
            Path(__file__).resolve().parents[3] / "control-plane" / "default-skills",
        )
    ),
]
TARGET_SKILLS = (
    "prd-feature-understanding-skill",
    "analyze-functional-requirements",
    "generate-solution-test-points",
    "generate-solution-test-cases",
)


class RequirementAnswerHandoffSkillTests(unittest.TestCase):
    def test_all_requirement_skills_state_answer_handoff_rule(self):
        checked = 0
        for root in SKILL_ROOTS:
            for name in TARGET_SKILLS:
                path = root / name / "SKILL.md"
                if not path.is_file():
                    continue
                content = path.read_text(encoding="utf-8")
                self.assertRegex(
                    content, r"回写到对应事实|落实到业务事实|用户已经回答的问题|已回答的问题必须"
                )
                self.assertRegex(
                    content,
                    r"删除.*(问题|openQuestions|questions)|仅保留答复未覆盖",
                )
                checked += 1
        self.assertGreaterEqual(checked, len(TARGET_SKILLS))


if __name__ == "__main__":
    unittest.main()
