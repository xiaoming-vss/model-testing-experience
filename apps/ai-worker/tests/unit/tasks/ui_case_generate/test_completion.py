import unittest
from copy import deepcopy

from testing_agent_ai_worker.tasks.ui_case_generate.completion import compile_case, xpath_literal


def draft():
    return dict(
        draftVersion="ui_yaml_draft/2.0",
        name="发布数据转换",
        enabled=True,
        orderNo=1,
        dataRequirements=[
            dict(
                id="release",
                title="已完成打包的发布数据",
                fields={
                    "id": dict(label="发布数据ID", value=None),
                    "version": dict(label="版本名称", value=None),
                },
                conditions=["已完成打包且无进行中的转换任务"],
                confirmed=False,
            )
        ],
        designConflicts=[],
        stepsJson=[
            dict(
                orderNo=1,
                stepName="勾选发布数据",
                keyword="click",
                locatorType="xpath",
                locatorValue=None,
                dataBindings={
                    "locatorValue": "//tr[td[1]={{data.release.id|xpath}}]//input[@type='checkbox']"
                },
                sourceRefs=["action:A1"],
                purpose="business",
                enabled=True,
                continueOnFailure=False,
            ),
            dict(
                orderNo=2,
                stepName="核对发布数据",
                keyword="assert_text",
                locatorType="xpath",
                locatorValue=None,
                operationValue=None,
                comparator="eq",
                dataBindings={
                    "locatorValue": "//tr[td[1]={{data.release.id|xpath}}]/td[2]",
                    "operationValue": "{{data.release.version}}",
                },
                sourceRefs=["expectation:E1"],
                purpose="business",
                enabled=True,
                continueOnFailure=False,
            ),
        ],
    )


class CompletionTests(unittest.TestCase):
    def test_fill_once_updates_all_references_and_preserves_metadata_for_reedit(self):
        value = draft()
        before = deepcopy(value)
        pending = compile_case(value, for_validation=True)
        self.assertEqual(pending["stepsJson"][0]["missingFields"][0]["fields"], ["locatorValue"])
        self.assertNotIn("missingFields", value["stepsJson"][0])
        self.assertEqual(value, before)
        root = value["dataRequirements"][0]
        root["fields"]["id"]["value"] = "19"
        root["fields"]["version"]["value"] = "lerobot-A"
        root["confirmed"] = True
        resolved = compile_case(value)
        self.assertIn("td[1]='19'", resolved["stepsJson"][0]["locatorValue"])
        self.assertIn("td[1]='19'", resolved["stepsJson"][1]["locatorValue"])
        self.assertEqual(resolved["stepsJson"][1]["operationValue"], "lerobot-A")
        resolved["dataRequirements"][0]["fields"]["id"]["value"] = "23"
        self.assertIn("td[1]='23'", compile_case(resolved)["stepsJson"][0]["locatorValue"])
        executable = compile_case(resolved, complete=True)
        self.assertNotIn("dataRequirements", executable)
        self.assertNotIn("dataBindings", executable["stepsJson"][0])

    def test_import_blocks_unfilled_unconfirmed_or_conflicting_draft(self):
        value = draft()
        with self.assertRaises(ValueError):
            compile_case(value, complete=True)
        for f in value["dataRequirements"][0]["fields"].values():
            f["value"] = "已提供"
        with self.assertRaises(ValueError):
            compile_case(value, complete=True)
        value["dataRequirements"][0]["confirmed"] = True
        value["designConflicts"] = [
            dict(
                sourceRefs=["expectation:E1"],
                reason="运行中新ID无法捕获",
                requiredCapability="变量提取",
            )
        ]
        with self.assertRaises(ValueError):
            compile_case(value, complete=True)

    def test_xpath_values_are_quoted_and_do_not_change_selector_structure(self):
        self.assertEqual(xpath_literal("a'b"), '"a\'b"')
        self.assertEqual(xpath_literal('a"b'), "'a\"b'")
        both = xpath_literal("a'b\"c")
        self.assertTrue(both.startswith("concat("))
        value = draft()
        value["dataRequirements"][0]["fields"]["id"]["value"] = "' or true() or '"
        resolved = compile_case(value)
        self.assertIn("td[1]=\"' or true() or '\"", resolved["stepsJson"][0]["locatorValue"])

    def test_independent_locator_gap_remains_after_data_completion(self):
        value = draft()
        s = value["stepsJson"][0]
        s.pop("dataBindings")
        s["locatorType"] = None
        s["missingFields"] = [
            dict(
                fields=["locatorType", "locatorValue"],
                operation="定位勾选框",
                target="已识别记录的勾选框",
                value=None,
                reason="该控件渲染结构无证据",
            )
        ]
        for f in value["dataRequirements"][0]["fields"].values():
            f["value"] = "provided"
        value["dataRequirements"][0]["confirmed"] = True
        self.assertTrue(compile_case(value)["stepsJson"][0]["missingFields"])
        with self.assertRaises(ValueError):
            compile_case(value, complete=True)

    def test_unknown_reference_and_duplicate_gap_rejected(self):
        value = draft()
        value["stepsJson"][0]["dataBindings"]["locatorValue"] = "//tr[td={{data.other.id|xpath}}]"
        with self.assertRaises(ValueError):
            compile_case(value)
        value = draft()
        value["stepsJson"][0]["missingFields"] = [dict(fields=["locatorValue"])]
        with self.assertRaises(ValueError):
            compile_case(value)
        value = draft()
        value["dataRequirements"].append(
            {**deepcopy(value["dataRequirements"][0]), "id": "duplicate"}
        )
        with self.assertRaises(ValueError):
            compile_case(value)


class InlineCompletionTests(unittest.TestCase):
    def test_inline_reference_becomes_a_reusable_binding(self):
        value = draft()
        step = value["stepsJson"][0]
        step["locatorValue"] = step.pop("dataBindings")["locatorValue"]
        normalized = compile_case(value)
        self.assertIsNone(normalized["stepsJson"][0]["locatorValue"])
        self.assertIn("locatorValue", normalized["stepsJson"][0]["dataBindings"])
        normalized["dataRequirements"][0]["fields"]["id"]["value"] = "19"
        self.assertIn("'19'", compile_case(normalized)["stepsJson"][0]["locatorValue"])

    def test_xpath_reference_inside_quotes_is_rejected(self):
        value = draft()
        value["stepsJson"][0]["dataBindings"]["locatorValue"] = (
            "//tr[td='{{data.release.id|xpath}}']"
        )
        with self.assertRaisesRegex(ValueError, "引号内"):
            compile_case(value)

    def test_url_query_values_are_encoded_without_changing_data(self):
        value = draft()
        value["dataRequirements"][0]["fields"]["id"]["value"] = "19&other=20"
        value["stepsJson"][0] = dict(
            keyword="open", operationValue="https://example.invalid/records?id={{data.release.id}}"
        )
        result = compile_case(value)
        self.assertEqual(
            result["stepsJson"][0]["operationValue"],
            "https://example.invalid/records?id=19%26other%3D20",
        )
        self.assertEqual(result["dataRequirements"][0]["fields"]["id"]["value"], "19&other=20")

    def test_malformed_missing_fields_is_a_repairable_validation_error(self):
        for pending in ([{"fields": None}], [{"fields": [{}]}], ["invalid"]):
            value = draft()
            value["stepsJson"][0]["missingFields"] = pending
            with self.subTest(pending=pending), self.assertRaisesRegex(ValueError, "fields"):
                compile_case(value)
