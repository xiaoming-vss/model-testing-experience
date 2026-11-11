import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_scenarios import DEFAULT_CAPABILITIES, validate


def fixture():
    original = {
        "caseId": "C1",
        "title": "查询指定任务",
        "content": {
            "preconditions": ["已登录", "准备指定任务"],
            "steps": [
                {"action": "打开页面，输入任务ID。", "expected": "显示指定任务。"}
            ],
        },
    }
    design = {
        "caseId": "C1",
        "name": "查询指定任务",
        "sourceTitle": original["title"],
        "preconditions": original["content"]["preconditions"][:],
        "goal": "找到指定任务",
        "coreExpectationIds": ["E1"],
        "coverage": "full",
        "limitations": [],
        "steps": [
            {
                "sourceStepNo": 1,
                "sourceAction": "打开页面，输入任务ID。",
                "actions": [
                    {
                        "actionId": "A1",
                        "sourceQuote": "打开页面，",
                        "action": "打开页面",
                        "operation": "navigate",
                        "target": "任务页面",
                        "value": None,
                        "status": "included",
                    },
                    {
                        "actionId": "A2",
                        "sourceQuote": "输入任务ID。",
                        "action": "输入任务ID",
                        "operation": "input",
                        "target": "任务ID输入框",
                        "value": None,
                        "status": "included",
                    },
                ],
                "expectations": [
                    {
                        "expectationId": "E1",
                        "sourceQuote": "显示指定任务。",
                        "assertion": "text_eq",
                        "target": "任务ID单元格",
                        "value": None,
                        "status": "included",
                    }
                ],
            }
        ],
    }
    return {"cases": [original]}, {
        "schemaVersion": "ui_test_scenarios/2.0",
        "capabilities": copy.deepcopy(DEFAULT_CAPABILITIES),
        "cases": [design],
    }


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.source, self.report = fixture()

    def errors(self, **kwargs):
        return validate(self.report, cases=self.source, **kwargs)

    def test_missing_surface_and_values_do_not_block_design(self):
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.errors(surface={"controls": []}), [])
        self.assertEqual(
            self.errors(surface={"controls": [{"broken": "irrelevant"}]}), []
        )

    def test_precondition_cannot_be_dropped(self):
        self.report["cases"][0]["preconditions"].pop()
        self.assertTrue(self.errors())

    def test_expected_clause_cannot_be_omitted(self):
        self.report["cases"][0]["steps"][0]["expectations"] = []
        self.assertTrue(self.errors())

    def test_missing_locator_is_not_a_capability_exclusion(self):
        action = self.report["cases"][0]["steps"][0]["actions"][1]
        action.update(status="excluded", reason="找不到输入框")
        self.report["cases"][0].update(coverage="partial", limitations=["找不到"])
        self.assertTrue(any("unsupported capability" in e for e in self.errors()))

    def test_compound_action_keeps_supported_part(self):
        step = self.report["cases"][0]["steps"][0]
        self.source["cases"][0]["content"]["steps"][0]["action"] = (
            "打开页面，捕获全部ID。"
        )
        step["sourceAction"] = "打开页面，捕获全部ID。"
        step["actions"][1].update(
            sourceQuote="捕获全部ID。",
            action="捕获全部ID",
            operation="variable_capture",
            status="excluded",
            reason="平台不支持捕获集合",
        )
        self.report["cases"][0].update(
            coverage="partial", limitations=["先准备固定任务ID，再执行保留的查询检查"]
        )
        self.assertEqual(self.errors(), [])
        self.assertEqual(step["actions"][0]["status"], "included")

    def test_core_exclusion_requires_limitation(self):
        case = self.report["cases"][0]
        case["steps"][0]["expectations"][0].update(
            assertion="set_eq", status="excluded", reason="无集合断言"
        )
        case["coverage"] = "partial"
        self.assertTrue(any("limitations" in e for e in self.errors()))
        case["limitations"] = ["核心集合等价目标未覆盖"]
        self.assertEqual(self.errors(), [])

    def test_forged_capability_profile_rejected(self):
        self.report["capabilities"]["assertions"].append("set_eq")
        self.assertTrue(self.errors())

    def test_execution_binding_rejected(self):
        self.report["cases"][0]["steps"][0]["actions"][0]["locatorValue"] = "#guess"
        self.assertTrue(self.errors())

    def test_duplicate_or_missing_action_excerpt_rejected(self):
        step = self.report["cases"][0]["steps"][0]
        step["actions"][1]["sourceQuote"] = step["actions"][0]["sourceQuote"]
        self.assertTrue(self.errors())


if __name__ == "__main__":
    unittest.main()
