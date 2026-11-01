import asyncio
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from testing_agent_ai_worker.tasks.ui_case_generate.batches import (
    build_batches,
    generate_batches,
)
from tests.unit.tasks.ui_case_generate.test_three_stage import read


class BatchTests(unittest.TestCase):
    def fixtures(self, count=7):
        cases, designs = [], {}
        for i in range(count):
            case = deepcopy(read("cases")[0])
            case["caseId"] = str(i)
            case["module"] = "模块" + str(i % 2)
            cases.append(case)
            design = deepcopy(read("design")["cases"][0])
            design["caseId"] = str(i)
            designs[str(i)] = design
        return cases, designs

    def test_batch_repair_is_isolated_and_merge_restores_source_order(self):
        cases, designs = self.fixtures()
        calls, events = [], []
        original = dict(
            functionalCases=cases,
            cases=cases,
            surface=read("surface"),
            currentArtifact={**read("design"), "cases": list(designs.values())},
        )
        before = deepcopy(original)

        def generate(prompt, index, rules):
            body, _ = json.JSONDecoder().raw_decode(prompt)
            self.assertNotIn("outputPath", body)
            self.assertIn("JSON Schema", rules)
            ids = [c["caseId"] for c in body["functionalCases"]]
            self.assertEqual([c["caseId"] for c in body["currentArtifact"]["cases"]], ids)
            calls.append(index)
            result = {**read("design"), "cases": [deepcopy(designs[cid]) for cid in ids]}
            if index == 2 and calls.count(2) == 1:
                result["cases"][0]["steps"][0]["expectations"][0]["sourceQuote"] = "错误引用"
            return json.dumps(result)

        with tempfile.TemporaryDirectory() as root:
            result = asyncio.run(
                generate_batches(
                    body=original,
                    generate=generate,
                    instruction="",
                    user_instruction="",
                    diagnostic_dir=Path(root),
                    report=events.append,
                )
            )
        self.assertEqual([c["caseId"] for c in result["cases"]], [c["caseId"] for c in cases])
        self.assertEqual(calls, [1, 2, 2])
        self.assertEqual(original, before)
        self.assertTrue(any(e.get("repairAttempt") == 1 and e["batch"] == 2 for e in events))
        self.assertEqual(events[-1]["status"], "merged")

    def test_receipt_is_not_accepted_and_failure_stops_later_batches(self):
        cases, _ = self.fixtures()
        calls = []

        def generate(prompt, index, rules):
            calls.append(index)
            return '{"artifactPath":"ignored.json","status":"written"}'

        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
            asyncio.run(
                generate_batches(
                    body=dict(functionalCases=cases, surface=read("surface")),
                    generate=generate,
                    instruction="",
                    user_instruction="",
                    diagnostic_dir=Path(root),
                    report=lambda _: None,
                )
            )
        self.assertEqual(calls, [1, 1, 1])

    def test_large_module_stays_one_batch(self):
        cases, _ = self.fixtures(30)
        for case in cases:
            case["module"] = "同模块"
        cases[1]["content"]["steps"] *= 20
        cases[1]["title"] = "长" * 7000
        batches = build_batches(cases)
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0], cases)

    def test_foreign_or_duplicate_case_cannot_pass_a_batch(self):
        cases, designs = self.fixtures(1)
        for duplicate in (True, False):
            calls = []

            def generate(prompt, index, rules):
                calls.append(index)
                rows = [deepcopy(designs["0"])]
                if duplicate:
                    rows.append(deepcopy(rows[0]))
                else:
                    rows[0]["caseId"] = "foreign"
                return json.dumps({**read("design"), "cases": rows})

            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):
                    asyncio.run(
                        generate_batches(
                            body=dict(functionalCases=cases, surface=read("surface")),
                            generate=generate,
                            instruction="",
                            user_instruction="",
                            diagnostic_dir=Path(root),
                            report=lambda _: None,
                        )
                    )
            self.assertEqual(calls, [1, 1, 1])
