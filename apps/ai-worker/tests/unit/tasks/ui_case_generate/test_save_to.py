import copy
import unittest

import yaml

from testing_agent_ai_worker.tasks.ui_case_generate.executor import _validate_ui_stage_yaml


class SaveToGenerationTests(unittest.TestCase):
    def payload(self):
        return [
            {
                "name": "创建后复用ID",
                "enabled": True,
                "orderNo": 1,
                "stepsJson": [
                    {
                        "orderNo": 1,
                        "stepName": "保存ID",
                        "keyword": "assert_visible",
                        "locatorType": "xpath",
                        "locatorValue": "//tr[td={{name|xpath}}]/td[1]",
                        "operationValue": 1000,
                        "enabled": True,
                        "continueOnFailure": False,
                        "saveTo": [{"name": "recordId", "source": "text"}],
                    },
                    {
                        "orderNo": 2,
                        "stepName": "查询ID",
                        "keyword": "input",
                        "locatorType": "test_id",
                        "locatorValue": "query",
                        "operationValue": "{{recordId}}",
                        "enabled": True,
                        "continueOnFailure": False,
                    },
                ],
            }
        ]

    def test_stage_accepts_capture_then_reuse_without_mutating_output(self):
        rows = self.payload()
        before = copy.deepcopy(rows)
        self.assertEqual(1, _validate_ui_stage_yaml(yaml.safe_dump(rows)))
        self.assertEqual(before, rows)

    def test_stage_rejects_invalid_extraction_rules(self):
        for rule in [
            {"name": "baseUrl", "source": "text"},
            {"name": "id", "source": "regex"},
            {"name": "id", "source": "attribute"},
            {"name": "id", "source": "text", "locatorType": "css"},
            {"name": "id", "source": "text", "locatorType": "css", "locatorValue": "{{row}}"},
            {"name": "id", "source": "text", "script": "return 1"},
        ]:
            with self.subTest(rule=rule):
                rows = self.payload()
                rows[0]["stepsJson"][0]["saveTo"] = [rule]
                with self.assertRaises(ValueError):
                    _validate_ui_stage_yaml(yaml.safe_dump(rows))

    def test_stage_accepts_url_extraction_and_variable_timeout(self):
        rows = self.payload()
        rows[0]["stepsJson"][0]["operationValue"] = "{{waitMs}}"
        rows[0]["stepsJson"][0]["saveTo"] = [{"name": "pageUrl", "source": "url"}]
        self.assertEqual(1, _validate_ui_stage_yaml(yaml.safe_dump(rows)))

    def test_stage_rejects_unsafe_xpath_variable(self):
        rows = self.payload()
        step = rows[0]["stepsJson"][0]
        step.pop("saveTo")
        step["locatorValue"] = "//tr[td='{{name}}']"
        with self.assertRaises(ValueError):
            _validate_ui_stage_yaml(yaml.safe_dump(rows))
