import unittest
from copy import deepcopy

from support.ui_completion import draft

from testing_agent.domain.ui_completion import compile_case, xpath_literal


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


class CompletionBoundaryTests(unittest.TestCase):
    def test_draft_save_renders_all_bindings_and_import_strips_metadata(self):
        from types import SimpleNamespace

        import yaml

        from testing_agent.services.ui_generation_contracts import validate_ui_output
        from testing_agent.services.ui_test_case import validate_ui_import_payload

        value = draft()
        for field, content in [("id", "0019"), ("version", "version-A")]:
            value["dataRequirements"][0]["fields"][field]["value"] = content
        value["dataRequirements"][0]["confirmed"] = True
        run = SimpleNamespace(snapshot_json={"functionalCases": [{}]})
        rendered = validate_ui_output(run, "ui_yaml", yaml.safe_dump([value]))
        rows = yaml.safe_load(rendered)
        self.assertIn("'0019'", rows[0]["stepsJson"][0]["locatorValue"])
        self.assertEqual(rows[0]["stepsJson"][1]["operationValue"], "version-A")
        executable = validate_ui_import_payload({"items": rows})
        self.assertNotIn("dataRequirements", executable[0])
        self.assertNotIn("dataBindings", executable[0]["stepsJson"][0])

    def test_direct_import_cannot_bypass_unfilled_roots(self):
        from testing_agent.core.errors import AppError
        from testing_agent.services.ui_test_case import validate_ui_import_payload

        with self.assertRaises(AppError):
            validate_ui_import_payload({"items": [draft()]})


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
