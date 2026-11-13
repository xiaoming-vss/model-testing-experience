import contextlib
import copy
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_ui_case import validate_case


def fixture():
    return {
        "name": "选择格式",
        "enabled": True,
        "orderNo": 1,
        "stepsJson": [
            {
                "orderNo": 1,
                "stepName": "选择 LeRobot",
                "keyword": "click",
                "locatorType": None,
                "locatorValue": None,
                "missingFields": [
                    {
                        "fields": ["locatorType", "locatorValue"],
                        "operation": "选择格式",
                        "target": "格式选项",
                        "value": "LeRobot",
                        "reason": "缺少选项定位",
                    }
                ],
                "continueOnFailure": False,
                "enabled": True,
            },
            {
                "orderNo": 2,
                "stepName": "核对格式",
                "keyword": "assert_text",
                "locatorType": "test_id",
                "locatorValue": "selected-format",
                "operationValue": "LeRobot",
                "comparator": "eq",
                "continueOnFailure": False,
                "enabled": True,
            },
        ],
    }


class MissingTests(unittest.TestCase):
    def setUp(self):
        self.case = fixture()

    def validate(self, draft=False):
        with contextlib.redirect_stderr(io.StringIO()):
            validate_case(self.case, 1, "", False, False, allow_missing=draft)

    def test_draft_retains_known_expected_value(self):
        before = copy.deepcopy(self.case)
        self.validate(True)
        self.assertEqual(self.case, before)
        self.assertEqual(self.case["stepsJson"][1]["operationValue"], "LeRobot")

    def test_draft_cannot_pass_complete_gate(self):
        with self.assertRaises(SystemExit):
            self.validate()

    def test_human_completion_needs_no_bundle_trace_or_model(self):
        self.case["stepsJson"][0].update(
            locatorType="css", locatorValue=".n-select-option", missingFields=[]
        )
        self.validate()

    def test_removing_metadata_without_filling_fails(self):
        self.case["stepsJson"][0].pop("missingFields")
        with self.assertRaises(SystemExit):
            self.validate()

    def test_filling_without_resolving_metadata_fails(self):
        self.case["stepsJson"][0]["locatorValue"] = "#format"
        with self.assertRaises(SystemExit):
            self.validate(True)

    def test_prerequisite_without_platform_field_blocks(self):
        step = self.case["stepsJson"][0]
        step.update(locatorType="test_id", locatorValue="format")
        step["missingFields"][0].update(
            fields=[], target="可转换发布记录", reason="需要准备3条指定状态的记录"
        )
        self.validate(True)
        with self.assertRaises(SystemExit):
            self.validate()

    def test_disabled_missing_step_still_blocks(self):
        self.case["stepsJson"][0]["enabled"] = False
        with self.assertRaises(SystemExit):
            self.validate()

    def test_bad_metadata_rejected(self):
        for bad in [None, {}, "missing", [{}]]:
            with self.subTest(bad=bad):
                self.case = fixture()
                self.case["stepsJson"][0]["missingFields"] = bad
                with self.assertRaises(SystemExit):
                    self.validate(True)

    def test_unsupported_keyword_not_disguised_as_draft(self):
        self.case["stepsJson"][0]["keyword"] = "hover"
        with self.assertRaises(SystemExit):
            self.validate(True)

    def test_known_invalid_comparator_not_hidden_by_missing_locator(self):
        self.case["stepsJson"][1]["comparator"] = "regex"
        with self.assertRaises(SystemExit):
            self.validate(True)

    def test_missing_url_can_be_completed(self):
        step = self.case["stepsJson"][0]
        step.update(keyword="open", operationValue=None)
        del step["locatorType"]
        del step["locatorValue"]
        step["missingFields"][0].update(
            fields=["operationValue"],
            operation="打开页面",
            target="环境地址",
            value=None,
            reason="请提供完整目标URL",
        )
        self.validate(True)
        step.update(operationValue="https://fixture.example/tasks", missingFields=[])
        self.validate()

    def test_unknown_missing_field_rejected(self):
        self.case["stepsJson"][0]["missingFields"][0]["fields"] = ["madeUp"]
        with self.assertRaises(SystemExit):
            self.validate(True)

    def test_hidden_assertion_timeout_is_not_a_business_gap(self):
        step = self.case["stepsJson"][0]
        step.update(
            keyword="assert_hidden",
            locatorType="xpath",
            locatorValue="//div[contains(text(),'转换格式必填')]",
            operationValue=None,
        )
        step["missingFields"][0].update(
            fields=["operationValue"],
            operation="确认没有必填提示",
            target="转换格式必填提示",
            value=None,
            reason="缺少等待时间",
        )
        with self.assertRaises(SystemExit):
            self.validate(True)
        step.update(operationValue="3000", missingFields=[])
        self.validate()

    def test_deleting_unwanted_step_and_renumbering_is_supported(self):
        self.case["stepsJson"].pop(0)
        self.case["stepsJson"][0]["orderNo"] = 1
        self.validate()


if __name__ == "__main__":
    unittest.main()
