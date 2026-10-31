import asyncio
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import yaml

from testing_agent_ai_worker.tasks.ui_case_generate.executor import _validate_ui_stage_yaml
from testing_agent_ai_worker.tasks.ui_case_generate.yaml_batches import (
    generate_yaml_batches,
    validate_module,
)
from tests.unit.tasks.ui_case_generate.test_three_stage import FIXTURES, read


class YamlBatchTests(unittest.TestCase):
    def body(self):
        cases, designs = [], []
        for i, module in enumerate(["甲", "乙", "甲"]):
            case = deepcopy(read("cases")[0])
            case.update(caseId=str(i), module=module)
            cases.append(case)
            design = deepcopy(read("design")["cases"][0])
            design.update(caseId=str(i), name=f"用例{i}")
            designs.append(design)
        return dict(
            functionalCases=cases,
            cases=cases,
            surface=read("surface"),
            design={**read("design"), "cases": designs},
            sourceRoot="/source",
        )

    def run_batches(self, body, generate):
        events = []
        with tempfile.TemporaryDirectory() as root:
            result = asyncio.run(
                generate_yaml_batches(
                    body=body,
                    generate=generate,
                    instruction="",
                    user_instruction="",
                    diagnostic_dir=Path(root),
                    report=events.append,
                    validate_yaml=_validate_ui_stage_yaml,
                )
            )
        return yaml.safe_load(result), events

    def candidate(self, designs):
        rows = []
        for i, design in enumerate(designs, 1):
            row = yaml.safe_load((FIXTURES / "draft.yaml").read_text())[0]
            row.update(name=design["name"], orderNo=i)
            rows.append(row)
        return rows

    def test_only_failed_module_repaired_then_reordered_and_renumbered(self):
        body = self.body()
        before = deepcopy(body)
        calls = []

        def generate(prompt, index, rules):
            inputs, _ = json.JSONDecoder().raw_decode(prompt)
            self.assertNotIn("outputPath", inputs)
            self.assertEqual(
                json.loads(Path(inputs["reviewedDesignPath"]).read_text()), inputs["design"]
            )
            self.assertEqual(
                [c["caseId"] for c in inputs["functionalCases"]],
                [c["caseId"] for c in inputs["design"]["cases"]],
            )
            calls.append(index)
            rows = self.candidate(inputs["design"]["cases"])
            if index == 2 and calls.count(2) == 1:
                rows = []
            return yaml.safe_dump(rows, allow_unicode=True)

        rows, events = self.run_batches(body, generate)
        self.assertEqual(calls, [1, 2, 2])
        self.assertEqual([r["name"] for r in rows], ["用例0", "用例1", "用例2"])
        self.assertEqual([r["orderNo"] for r in rows], [1, 2, 3])
        self.assertTrue(rows[0]["stepsJson"][1]["missingFields"])
        self.assertEqual(body, before)
        self.assertEqual(events[-1]["status"], "merged")

    def test_excluded_module_needs_no_generation(self):
        body = self.body()
        for case in body["design"]["cases"]:
            case["coverage"] = "excluded"
        rows, _ = self.run_batches(
            body, lambda *args: self.fail("excluded cases must not generate")
        )
        self.assertEqual(rows, [])

    def test_wrong_case_or_empty_steps_fails_without_partial_publication(self):
        for wrong_name in (True, False):
            calls = []

            def generate(prompt, index, rules):
                inputs, _ = json.JSONDecoder().raw_decode(prompt)
                calls.append(index)
                rows = self.candidate(inputs["design"]["cases"])
                if wrong_name:
                    rows[0]["name"] = "其他模块"
                else:
                    rows[0]["stepsJson"] = []
                return yaml.safe_dump(rows, allow_unicode=True)

            with self.subTest(wrong_name=wrong_name), self.assertRaises(ValueError):
                self.run_batches(self.body(), generate)
            self.assertEqual(calls, [1, 1, 1])

    def test_revision_receives_only_its_current_yaml_cases(self):
        body = self.body()
        body["currentArtifact"] = yaml.safe_dump(
            self.candidate(body["design"]["cases"]), allow_unicode=True
        )

        def generate(prompt, index, rules):
            inputs, _ = json.JSONDecoder().raw_decode(prompt)
            current = yaml.safe_load(inputs["currentArtifact"])
            self.assertEqual(
                [r["name"] for r in current], [d["name"] for d in inputs["design"]["cases"]]
            )
            self.assertEqual([r["orderNo"] for r in current], list(range(1, len(current) + 1)))
            return inputs["currentArtifact"]

        rows, _ = self.run_batches(body, generate)
        self.assertEqual(len(rows), 3)

    def test_new_generation_rejects_expanded_format_for_all_cases(self):
        designs = self.body()["design"]["cases"]
        rows = self.candidate(designs)
        for row in rows:
            row["dataRequirements"] = []
            row["stepsJson"][0]["sourceRefs"] = []
        with self.assertRaisesRegex(ValueError, "原始") as caught:
            validate_module(
                yaml.safe_dump(rows, allow_unicode=True),
                designs,
                _validate_ui_stage_yaml,
                require_legacy=True,
            )
        self.assertEqual(str(caught.exception).count('"caseIndex"'), 3)

    def test_historical_expanded_revision_preserves_values_without_reusing_its_format(self):
        body = self.body()
        rows = self.candidate(body["design"]["cases"])
        for row in rows:
            row.update(
                draftVersion="ui_yaml_draft/2.0",
                dataRequirements=[
                    dict(
                        id="env",
                        title="环境",
                        fields={"url": dict(label="URL", value="https://target.test/records")},
                        conditions=[],
                        confirmed=False,
                    )
                ],
                designConflicts=[],
            )
            step = row["stepsJson"][0]
            step.pop("missingFields")
            step["dataBindings"] = {"operationValue": "{{data.env.url}}"}
        body["currentArtifact"] = yaml.safe_dump(rows, allow_unicode=True)

        def generate(prompt, index, rules):
            inputs, _ = json.JSONDecoder().raw_decode(prompt)
            current = yaml.safe_load(inputs["currentArtifact"])
            for row in current:
                self.assertEqual(set(row), {"name", "enabled", "stepsJson", "orderNo"})
                self.assertEqual(
                    row["stepsJson"][0]["operationValue"], "https://target.test/records"
                )
                self.assertNotIn("dataBindings", row["stepsJson"][0])
            return inputs["currentArtifact"]

        result, _ = self.run_batches(body, generate)
        self.assertEqual(len(result), 3)

    def test_expanded_output_is_repaired_before_merge(self):
        calls = []

        def generate(prompt, index, rules):
            inputs, _ = json.JSONDecoder().raw_decode(prompt)
            calls.append(index)
            rows = self.candidate(inputs["design"]["cases"])
            if len(calls) == 1:
                rows[0]["dataRequirements"] = []
            return yaml.safe_dump(rows, allow_unicode=True)

        rows, _ = self.run_batches(self.body(), generate)
        self.assertEqual(calls, [1, 1, 2])
        self.assertTrue(
            all(set(row) == {"name", "enabled", "stepsJson", "orderNo"} for row in rows)
        )
