import json
import unittest
from copy import deepcopy
from pathlib import Path

from testing_agent_ai_worker.requirement_artifacts import requirement_content, validate_artifact

FIXTURES = Path(__file__).resolve().parents[4] / "tests/fixtures/requirement_artifacts"
KIND = "requirement_understanding"


class CompactContractTests(unittest.TestCase):
    def setUp(self):
        self.compact = json.loads((FIXTURES / "requirement-understanding.example.json").read_text())

    def test_round_trip_retains_facts_questions_and_sources(self):
        self.assertEqual(validate_artifact(self.compact, KIND), self.compact)
        self.assertEqual(json.loads(requirement_content(self.compact)), self.compact)
        refs = [(e["sourceId"], e["locator"], e.get("excerpt")) for e in self.compact["evidence"]]
        self.assertEqual(len(refs), len(set(refs)))

    def test_confirmed_default_requires_real_nonexample_evidence(self):
        fact = self.compact["businessRules"][0]["expectedBehavior"][0]
        fact.pop("confirmationStatus")
        with self.assertRaisesRegex(ValueError, "示例来源"):
            validate_artifact(self.compact, KIND)
        self.compact["sources"][0]["type"] = "document"
        validate_artifact(self.compact, KIND)
        fact.pop("evidenceIds")
        with self.assertRaises(ValueError):
            validate_artifact(self.compact, KIND)

    def test_invalid_reference_duplicate_and_unknown_version_rejected(self):
        mutations = [
            lambda d: d["evidence"].append(deepcopy(d["evidence"][0])),
            lambda d: d["evidence"][0].update(sourceId="missing"),
            lambda d: d["modules"][0]["purpose"].update(evidenceIds=["missing"]),
            lambda d: d.update(schemaVersion="1.0"),
            lambda d: d.update(schemaVersion="3.0"),
            lambda d: d.update(schemaVersion=[]),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data = deepcopy(self.compact)
                mutate(data)
                with self.assertRaises(ValueError):
                    validate_artifact(data, KIND)

    def test_narrative_and_rule_branch_without_duplicated_condition(self):
        self.compact["modules"][0]["purpose"] = "查看列表并执行筛选"
        branch = {"stepId": None}
        self.compact["businessFlows"][0]["steps"][0]["nextSteps"] = [branch]
        branch["conditionRuleIds"] = [self.compact["businessRules"][0]["id"]]
        validate_artifact(self.compact, KIND)
        self.assertNotIn(
            "condition",
            json.loads(requirement_content(self.compact))["businessFlows"][0]["steps"][0][
                "nextSteps"
            ][0],
        )
        branch["conditionRuleIds"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "conditionRuleIds"):
            validate_artifact(self.compact, KIND)

    def test_null_cannot_silently_become_confirmed(self):
        self.compact["modules"][0]["purpose"] = {"value": None, "evidenceIds": ["EV001"]}
        with self.assertRaises(ValueError):
            validate_artifact(self.compact, KIND)

    def test_conflict_requires_open_question_and_keeps_status(self):
        fact = self.compact["businessRules"][0]["expectedBehavior"][0]
        fact["confirmationStatus"] = "conflicting"
        with self.assertRaises(ValueError):
            validate_artifact(self.compact, KIND)
        fact["relatedQuestionIds"] = [self.compact["questions"][0]["id"]]
        validate_artifact(self.compact, KIND)
        self.assertEqual(
            self.compact["businessRules"][0]["expectedBehavior"][0]["confirmationStatus"],
            "conflicting",
        )

    def test_partial_confirmed_answer_survives_revision(self):
        self.compact["sources"][0]["type"] = "user_confirmation"
        answer = deepcopy(self.compact["businessRules"][0]["expectedBehavior"][0])
        answer.pop("confirmationStatus")
        self.compact["questions"][0]["answer"] = answer
        validate_artifact(self.compact, KIND)
        self.assertEqual(json.loads(requirement_content(self.compact)), self.compact)
        self.compact["questions"][0]["status"] = "resolved"
        validate_artifact(self.compact, KIND, allow_resolved_questions=True)
        with self.assertRaisesRegex(ValueError, "已解决问题"):
            validate_artifact(self.compact, KIND)

    def test_inline_source_references_are_rejected(self):
        self.compact["modules"][0]["purpose"]["sourceReferences"] = []
        with self.assertRaises(ValueError):
            validate_artifact(self.compact, KIND)
