"""Read frozen trial metadata without acquiring or approving business sources."""

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from testing_agent_ai_worker.platform.generation_candidates import FrozenCandidateInput

FIXTURE = Path(__file__).resolve().parents[5] / "tests/fixtures/generation-candidate-contract.json"


class CandidateContractTests(unittest.TestCase):
    def test_trial_metadata_keeps_explicit_source_identity(self):
        fixture = json.loads(FIXTURE.read_text())
        value = FrozenCandidateInput.model_validate(fixture["frozenTrialInput"])
        self.assertEqual(value.generation_mode, "trial")
        self.assertEqual(value.sources[0].snapshot_id, "snapshot-a")
        self.assertEqual(value.sources[0].source_kind, "candidate")
        self.assertEqual(value.model_dump(by_alias=True), fixture["frozenTrialInput"])

    def test_unknown_mode_does_not_become_approved_input(self):
        fixture = json.loads(FIXTURE.read_text())["frozenTrialInput"]
        fixture["generationMode"] = "approved"
        with self.assertRaises(ValidationError):
            FrozenCandidateInput.model_validate(fixture)

    def test_current_selection_can_reference_the_same_previously_selected_candidate(self):
        fixture = json.loads(FIXTURE.read_text())["frozenTrialInput"]
        fixture["generationMode"] = "current"
        fixture["selectedSources"][0]["sourceKind"] = "current"
        result = FrozenCandidateInput.model_validate(fixture)
        self.assertEqual(result.selected_sources[0].source_kind, "current")
        self.assertEqual(result.sources[0].source_kind, "candidate")
        fixture["selectedSources"][0]["snapshotId"] = "different-snapshot"
        with self.assertRaises(ValidationError):
            FrozenCandidateInput.model_validate(fixture)


class CandidateSnapshotProtocolTests(unittest.TestCase):
    def test_worker_keeps_verified_metadata_without_adding_it_to_model_input(self):
        from testing_agent_ai_worker.platform.schemas import (
            PlatformClaimTask,
            PlatformSnapshotResponse,
        )
        from testing_agent_ai_worker.platform.task_source import HttpClaimTaskSource

        fixture = json.loads(FIXTURE.read_text())["frozenTrialInput"]
        raw = {
            "candidateProtocol": "single-current/1",
            "candidateInput": fixture,
            "run": {"taskId": "task", "sourceContent": "selected content"},
        }
        parsed = PlatformSnapshotResponse.model_validate(raw)
        claim = PlatformClaimTask.model_validate({"taskId": "task", "attemptId": "attempt"})
        source = HttpClaimTaskSource(None, "", "", "", "worker")
        task = source._to_domain_task(claim, parsed, raw_snapshot=raw)
        self.assertEqual(task.candidate_input, fixture)
        self.assertEqual(task.payload.source_content, "selected content")
        self.assertNotIn("candidateInput", task.payload.metadata)

    def test_legacy_and_invalid_candidate_protocols(self):
        from testing_agent_ai_worker.platform.schemas import PlatformSnapshotResponse

        self.assertIsNone(
            PlatformSnapshotResponse.model_validate({"run": {"taskId": "t"}}).candidate_input
        )
        for payload in (
            {"candidateProtocol": "single-current/1"},
            {"candidateInput": json.loads(FIXTURE.read_text())["frozenTrialInput"]},
            {"candidateProtocol": "unknown", "candidateInput": {}},
        ):
            with self.assertRaises(ValidationError):
                PlatformSnapshotResponse.model_validate({"run": {"taskId": "t"}, **payload})
