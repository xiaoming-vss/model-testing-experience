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
    "mtx-analyze-functional-requirements",
    "mtx-generate-traceable-test-points",
    "mtx-generate-solution-test-cases",
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
                if name == "mtx-analyze-functional-requirements":
                    prompt = root / name / "prompts" / "scope-analysis.md"
                    self.assertIn("prompts/scope-analysis.md", content)
                    self.assertIn(
                        "先将答复补充到材料整理并审核", prompt.read_text(encoding="utf-8")
                    )
                    checked += 1
                    continue
                if name == "mtx-generate-traceable-test-points":
                    self.assertIn("新增业务答复须先补充到材料整理并审核", content)
                    checked += 1
                    continue
                self.assertIn("答复先回到材料整理", content)
                self.assertIn("本阶段只读取冻结输入", content)
                material_prompt = (
                    root
                    / "mtx-organize-requirement-material"
                    / "prompts"
                    / "material-organizing.md"
                ).read_text(encoding="utf-8")
                self.assertIn("删除已解决", material_prompt)
                self.assertIn("部分答复只保留", material_prompt)
                checked += 1
        self.assertGreaterEqual(checked, len(TARGET_SKILLS))


if __name__ == "__main__":
    unittest.main()
