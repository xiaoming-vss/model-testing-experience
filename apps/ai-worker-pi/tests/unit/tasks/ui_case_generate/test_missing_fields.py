import copy
import tempfile
import unittest
from unittest.mock import Mock

import yaml

from testing_agent_ai_worker_pi.models.execution import TaskStatus
from testing_agent_ai_worker_pi.tasks.ui_case_generate.executor import _validate_ui_cases_yaml
from tests.unit.tasks.ui_case_generate import test_repair


def draft():
    return [
        {
            "name": "人工补全",
            "enabled": True,
            "orderNo": 1,
            "stepsJson": [
                {
                    "orderNo": 1,
                    "stepName": "选择格式",
                    "keyword": "click",
                    "locatorType": None,
                    "locatorValue": None,
                    "enabled": True,
                    "continueOnFailure": False,
                    "missingFields": [
                        {
                            "fields": ["locatorType", "locatorValue"],
                            "operation": "选择格式",
                            "target": "LeRobot选项",
                            "value": "LeRobot",
                            "reason": "需要定位",
                        }
                    ],
                }
            ],
        }
    ]


class MissingFieldsTests(unittest.TestCase):
    def test_generation_returns_draft_without_repairing_away_missing_content(self):
        output = yaml.safe_dump(draft())
        runner = Mock(return_value=output)
        with tempfile.TemporaryDirectory() as root:
            result = test_repair.UiRepairTests().execute(root, runner, [])
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(result.output_yaml, output)
        runner.assert_called_once()

    def test_draft_accepted_without_mutation(self):
        data = draft()
        before = copy.deepcopy(data)
        self.assertEqual(_validate_ui_cases_yaml(yaml.safe_dump(data)), 1)
        self.assertEqual(data, before)

    def test_missing_metadata_is_not_a_general_bypass(self):
        data = draft()
        data[0]["stepsJson"][0]["keyword"] = "hover"
        with self.assertRaises(ValueError):
            _validate_ui_cases_yaml(yaml.safe_dump(data))

    def test_missing_null_without_metadata_rejected(self):
        data = draft()
        data[0]["stepsJson"][0].pop("missingFields")
        with self.assertRaises(ValueError):
            _validate_ui_cases_yaml(yaml.safe_dump(data))

    def test_completed_file_accepted(self):
        data = draft()
        data[0]["stepsJson"][0].update(
            locatorType="test_id", locatorValue="format", missingFields=[]
        )
        self.assertEqual(_validate_ui_cases_yaml(yaml.safe_dump(data)), 1)

    def test_wrong_metadata_rejected(self):
        for invalid in [None, {}, "pending", [{}]]:
            with self.subTest(invalid=invalid):
                data = draft()
                data[0]["stepsJson"][0]["missingFields"] = invalid
                with self.assertRaises(ValueError):
                    _validate_ui_cases_yaml(yaml.safe_dump(data))

    def test_stale_pending_field_rejected(self):
        data = draft()
        data[0]["stepsJson"][0]["locatorType"] = "test_id"
        with self.assertRaises(ValueError):
            _validate_ui_cases_yaml(yaml.safe_dump(data))

    def test_timeout_is_not_a_missing_business_expectation(self):
        data = draft()
        step = data[0]["stepsJson"][0]
        step.update(
            keyword="assert_visible",
            locatorType="xpath",
            locatorValue="//table",
            operationValue=None,
        )
        step["missingFields"][0].update(fields=["operationValue"], reason="缺少基线清单")
        with self.assertRaisesRegex(ValueError, "第 1 条.*第 1 个步骤.*milliseconds"):
            _validate_ui_cases_yaml(yaml.safe_dump(data))
        step.update(operationValue="5000", missingFields=[])
        self.assertEqual(_validate_ui_cases_yaml(yaml.safe_dump(data)), 1)

    def test_negative_assertion_timeout_is_not_a_missing_business_expectation(self):
        data = draft()
        step = data[0]["stepsJson"][0]
        step.update(
            keyword="assert_hidden",
            locatorType="xpath",
            locatorValue="//div[contains(text(),'转换格式必填')]",
            operationValue=None,
        )
        step["missingFields"][0].update(fields=["operationValue"], reason="缺少基线清单")
        with self.assertRaisesRegex(ValueError, "第 1 条.*第 1 个步骤.*milliseconds"):
            _validate_ui_cases_yaml(yaml.safe_dump(data))
        step.update(operationValue="5000", missingFields=[])
        self.assertEqual(_validate_ui_cases_yaml(yaml.safe_dump(data)), 1)

    def test_no_candidates_is_an_empty_result_not_fabricated_test(self):
        self.assertEqual(_validate_ui_cases_yaml("[]"), 0)


if __name__ == "__main__":
    unittest.main()
