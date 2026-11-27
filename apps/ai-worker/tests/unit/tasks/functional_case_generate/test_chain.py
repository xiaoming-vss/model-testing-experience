import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.agent.prompt import (
    FUNCTIONAL_ANALYSIS_JSON_ONLY_INSTRUCTION,
    FUNCTIONAL_CASE_NAMES_JSON_ONLY_INSTRUCTION,
    FUNCTIONAL_DETAILED_CASES_JSON_ONLY_INSTRUCTION,
)
from testing_agent_ai_worker.skill_names import SCOPE_SKILL, TEST_POINTS_SKILL
from testing_agent_ai_worker.tasks.functional_case_generate.chain import (
    _build_functional_case_names_body,
    run_functional_chain,
    run_functional_skill_step,
)
from testing_agent_ai_worker.tasks.functional_case_generate.detailed_batches import (
    _build_functional_detailed_case_body,
)
from tests.support.agent import FakeBot
from tests.unit.tasks.functional_case_generate.fixtures import analysis, material, traceable_points


def _reply(message: str) -> str:
    """Answer a functional-chain prompt the way the staged skills would."""
    if "本次审查类型" in message:
        return json.dumps({"issues": []})
    if f"请先加载本地 skill：{SCOPE_SKILL}" in message:
        return json.dumps(analysis(), ensure_ascii=False)
    if f"请先加载本地 skill：{TEST_POINTS_SKILL}" in message:
        return json.dumps(traceable_points(), ensure_ascii=False)
    return json.dumps({"cases": []}, ensure_ascii=False)


class FunctionalChainPromptTests(unittest.TestCase):
    def test_reviewed_analysis_is_passed_unchanged_to_both_downstream_stages(self) -> None:
        reviewed = json.dumps(analysis(), ensure_ascii=False)
        names = _build_functional_case_names_body(source_text="原始需求", analysis_json=reviewed)
        cases = _build_functional_detailed_case_body(
            source_text="原始需求", requirement_analysis_json=reviewed, case_names_json="{}"
        )
        self.assertEqual(
            names.split("【需求分析结果 JSON】\n\n", 1)[1].split("\n\n【输入版本】", 1)[0], reviewed
        )
        self.assertEqual(
            cases.split("【需求分析/测试点 JSON】\n\n", 1)[1].split("\n\n", 1)[0], reviewed
        )

    def test_run_functional_chain_appends_stage_specific_json_only_instructions(self) -> None:
        bot = FakeBot(_reply)

        def fake_from_config(**kwargs):
            return bot

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "skills/mtx-generate-traceable-test-points/references"
            ref.mkdir(parents=True)
            (ref / "design-audit.md").write_text("审查")
            (ref / "independent-review.md").write_text("审查协议")
            result = asyncio.run(
                run_functional_chain(
                    source_text=json.dumps(material(), ensure_ascii=False),
                    session_key="task:1",
                    analysis_skill_name="mtx-analyze-functional-requirements",
                    case_name_skill_name="mtx-generate-traceable-test-points",
                    detailed_case_skill_name="mtx-generate-solution-test-cases",
                    workspace=tmp,
                    extra_instruction="优先覆盖核心业务链路",
                    from_config=fake_from_config,
                )
            )
        self.assertEqual(result.detailed_cases_output, '{"cases": []}')
        self.assertEqual(len(bot.calls), 6)
        analysis_message, case_names_message = bot.calls[0]["message"], bot.calls[1]["message"]
        self.assertIn(FUNCTIONAL_ANALYSIS_JSON_ONLY_INSTRUCTION, analysis_message)
        self.assertIn("请先加载本地 skill：mtx-generate-traceable-test-points", case_names_message)
        self.assertIn(FUNCTIONAL_CASE_NAMES_JSON_ONLY_INSTRUCTION, case_names_message)
        self.assertIn("test_scope_impact_risk", case_names_message)
        self.assertEqual(sum("本次审查类型" in call["message"] for call in bot.calls), 3)
        self.assertIn(FUNCTIONAL_DETAILED_CASES_JSON_ONLY_INSTRUCTION, bot.calls[-1]["message"])

    def test_run_skill_step_appends_instruction_by_functional_skill_name(self) -> None:
        bot = FakeBot(_reply)

        def fake_from_config(**kwargs):
            return bot

        asyncio.run(
            run_functional_skill_step(
                input_text="登录需求",
                session_key="task:1",
                skill_name="mtx-analyze-functional-requirements",
                extra_instruction="只看功能路径",
                from_config=fake_from_config,
            )
        )

        self.assertEqual(len(bot.calls), 1)
        message = bot.calls[0]["message"]
        self.assertIn("只看功能路径", message)
        self.assertIn(FUNCTIONAL_ANALYSIS_JSON_ONLY_INSTRUCTION, message)


if __name__ == "__main__":
    unittest.main()
