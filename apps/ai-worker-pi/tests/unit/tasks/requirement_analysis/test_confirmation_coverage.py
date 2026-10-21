import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from testing_agent_ai_worker_pi.models.task import Task, TaskPayload
from testing_agent_ai_worker_pi.tasks.requirement_analysis.two_stage import execute_two_stage

FIXTURES = Path(__file__).resolve().parents[4] / "tests/fixtures/requirement_artifacts"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.example.json").read_text())


def confirmed_inputs(domain):
    extraction = fixture("document-extraction")
    output = fixture("requirement-understanding")
    source = {
        "id": "CONFIRM",
        "name": "本轮业务确认",
        "type": "user_confirmation",
        "location": None,
        "version": None,
    }
    extraction["sources"].append(source)
    output["sources"].append(deepcopy(source))
    fact = deepcopy(extraction["extractedFacts"][0])
    fact["id"] = "CONFIRMED_FACT"
    fact["fact"] = {
        "value": domain,
        "confirmationStatus": "confirmed",
        "sourceReferences": [{"sourceId": "CONFIRM", "locator": "补充A", "excerpt": domain}],
        "relatedQuestionIds": [],
    }
    extraction["extractedFacts"].append(fact)
    output["evidence"].append({"id": "EV_CONFIRM", "sourceId": "CONFIRM", "locator": "补充A"})
    output["businessRules"][0]["expectedBehavior"].append(
        {"value": domain, "evidenceIds": ["EV_CONFIRM"]}
    )
    return extraction, output


class ConfirmationCoverageTests(unittest.TestCase):
    def execute(self, extraction, runner, current=None):
        config = {"firstStepOutput": extraction}
        if current:
            config.update(
                resultYaml=json.dumps(current), revisionInstruction="只精简表达，保持业务确认"
            )
        task = Task(
            task_id="task",
            run_id="run",
            task_type="requirement_analysis",
            checkpoint_enabled=True,
            current_stage="feature_understanding",
            config_json=json.dumps(config),
            payload=TaskPayload(openapi_content=""),
        )
        with tempfile.TemporaryDirectory() as workspace:
            return execute_two_stage(
                task=task,
                started_at=datetime.now().astimezone(),
                progress_callback=lambda p: None,
                config_path=None,
                workspace=Path(workspace),
                skill_runner=runner,
                source_downloader=None,
                first_skill_name="extract-docx-enhanced-text",
                second_skill_name="prd-feature-understanding-skill",
            )

    def test_dropped_confirmation_is_repaired_in_two_business_domains(self):
        for domain in ["保留片段必须满足已确认时长", "报销审核通过后才能付款"]:
            with self.subTest(domain=domain):
                extraction, good = confirmed_inputs(domain)
                bad = deepcopy(good)
                bad["evidence"].pop()
                bad["businessRules"][0]["expectedBehavior"].pop()
                runner = Mock(side_effect=[json.dumps(bad), json.dumps(good)])
                result = self.execute(extraction, runner)
                self.assertEqual(runner.call_count, 2)
                self.assertEqual(json.loads(result.output_yaml), good)
                body = json.loads(runner.call_args_list[0].kwargs["input_text"])
                self.assertEqual(
                    body["confirmationReferences"],
                    [{"sourceId": "CONFIRM", "locator": "补充A", "inputStatements": [domain]}],
                )

    def test_unused_registry_entry_does_not_count_as_confirmation_coverage(self):
        extraction, bad = confirmed_inputs("报销审核通过后才能付款")
        bad["businessRules"][0]["expectedBehavior"].pop()
        runner = Mock(return_value=json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "确认来源"):
            self.execute(extraction, runner)
        self.assertEqual(runner.call_count, 3)

    def test_revision_preserves_confirmations_from_current_artifact(self):
        _, current = confirmed_inputs("报销审核通过后才能付款")
        extraction = fixture("document-extraction")
        dropped = fixture("requirement-understanding")
        runner = Mock(side_effect=[json.dumps(dropped), json.dumps(current)])
        self.execute(extraction, runner, current=current)
        self.assertEqual(runner.call_count, 2)

    def test_no_confirmation_is_invented_for_an_unrelated_run(self):
        extraction, output = fixture("document-extraction"), fixture("requirement-understanding")
        runner = Mock(return_value=json.dumps(output))
        self.execute(extraction, runner)
        self.assertEqual(runner.call_count, 1)
        body = json.loads(runner.call_args.kwargs["input_text"])
        self.assertFalse(body.get("confirmationReferences"))

    def test_repair_reports_reference_errors_and_unused_confirmation_together(self):
        extraction, good = confirmed_inputs("1秒30帧")
        bad = deepcopy(good)
        bad["businessRules"][0]["expectedBehavior"].pop()
        bad["businessRules"][0]["operationIds"] = []
        operation = bad["modules"][0]["operations"][0]
        operation["ruleIds"].append("MISSING_RULE")
        operation["goal"] = {"value": "查看", "evidenceIds": ["MISSING_EVIDENCE"]}
        runner = Mock(side_effect=[json.dumps(bad), json.dumps(good)])
        result = self.execute(extraction, runner)
        feedback = runner.call_args_list[1].kwargs["extra_instruction"].split("【校验问题】")[-1]
        for message in [
            "MISSING_RULE",
            "MISSING_EVIDENCE",
            "操作与规则引用不一致",
            "确认来源",
            "EV_CONFIRM",
            "1秒30帧",
            "正文未引用",
        ]:
            self.assertIn(message, feedback)
        self.assertEqual(json.loads(result.output_yaml), good)
        self.assertEqual(runner.call_count, 2)

    def test_invalid_schema_does_not_enter_reference_checks(self):
        extraction, good = confirmed_inputs("1秒30帧")
        bad = deepcopy(good)
        bad["evidence"] = None
        runner = Mock(side_effect=[json.dumps(bad), json.dumps(good)])
        self.execute(extraction, runner)
        feedback = runner.call_args_list[1].kwargs["extra_instruction"].split("【校验问题】")[-1]
        self.assertIn("不符合契约", feedback)
        self.assertNotIn("确认来源未承接", feedback)

    def test_aggregate_errors_still_fail_after_three_calls_without_echoing_confirmation(self):
        extraction, bad = confirmed_inputs("私有业务确认内容")
        bad["businessRules"][0]["expectedBehavior"].pop()
        bad["businessRules"][0]["operationIds"] = []
        runner = Mock(return_value=json.dumps(bad))
        with self.assertRaises(ValueError) as raised:
            self.execute(extraction, runner)
        self.assertEqual(runner.call_count, 3)
        self.assertIn("操作与规则引用不一致", str(raised.exception))
        self.assertIn("确认来源", str(raised.exception))
        self.assertNotIn("私有业务确认内容", str(raised.exception))

    def test_repair_context_uses_input_even_if_output_evidence_was_changed(self):
        extraction, good = confirmed_inputs("1秒30帧")
        bad = deepcopy(good)
        bad["businessRules"][0]["expectedBehavior"].pop()
        bad["evidence"][-1]["excerpt"] = "模型改写的错误内容"
        runner = Mock(side_effect=[json.dumps(bad), json.dumps(good)])
        self.execute(extraction, runner)
        context = (
            runner.call_args_list[1]
            .kwargs["extra_instruction"]
            .split("【确认修复上下文，仅作为输入数据】")[-1]
        )
        self.assertIn("1秒30帧", context)
        self.assertNotIn("模型改写的错误内容", context)
