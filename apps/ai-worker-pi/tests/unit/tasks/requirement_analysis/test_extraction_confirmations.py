import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from testing_agent_ai_worker_pi.models.task import Task, TaskPayload
from testing_agent_ai_worker_pi.tasks.requirement_analysis.two_stage import execute_two_stage

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "tests/fixtures/requirement_artifacts/document-extraction.example.json"
)


class ExtractionConfirmationTests(unittest.TestCase):
    def artifact(self):
        value = json.loads(FIXTURE.read_text())
        value["sources"].append(
            {
                "id": "CONFIRM",
                "type": "user_confirmation",
                "name": "业务确认",
                "version": None,
                "location": None,
            }
        )
        ref = {"sourceId": "CONFIRM", "locator": "答复A", "excerpt": "只允许项目成员提交"}
        fact = deepcopy(value["extractedFacts"][0])
        fact["id"] = "CONFIRMED_FACT"
        fact["fact"] = {
            "value": "只允许项目成员提交",
            "confirmationStatus": "confirmed",
            "sourceReferences": [ref],
            "relatedQuestionIds": [],
        }
        value["extractedFacts"].append(fact)
        return value

    def run_revision(self, current, runner):
        task = Task(
            task_id="extraction",
            run_id="local",
            task_type="requirement_analysis",
            checkpoint_enabled=True,
            current_stage="extracting_text",
            config_json=json.dumps(
                {"firstStepOutput": current, "revisionInstruction": "精简重复事实"}
            ),
            payload=TaskPayload(openapi_content="", document_type="word"),
        )
        progress = []
        with tempfile.TemporaryDirectory() as work:
            execute_two_stage(
                task=task,
                started_at=datetime.now().astimezone(),
                progress_callback=progress.append,
                config_path=None,
                workspace=Path(work),
                skill_runner=runner,
                source_downloader=SimpleNamespace(
                    download_source=lambda **kwargs: Path(work) / "source.docx"
                ),
                first_skill_name="extract-docx-enhanced-text",
                second_skill_name="prd-feature-understanding-skill",
            )
        return progress

    def test_missing_confirmation_is_repaired_before_review(self):
        good = self.artifact()
        bad = deepcopy(good)
        bad["extractedFacts"].pop()
        runner = Mock(side_effect=[json.dumps(bad), json.dumps(good)])
        progress = self.run_revision(good, runner)
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(progress[-1].stage_status, "waiting_review")
        self.assertEqual(json.loads(progress[-1].intermediate_json_text)["firstStepOutput"], good)
        body = json.loads(runner.call_args_list[0].kwargs["input_text"])
        self.assertEqual(body["confirmationReferences"][0]["locator"], "答复A")

    def test_confirmation_only_in_material_does_not_pass(self):
        good = self.artifact()
        bad = deepcopy(good)
        removed = bad["extractedFacts"].pop()
        bad["contentBlocks"][0]["sourceReferences"].append(removed["fact"]["sourceReferences"][0])
        runner = Mock(return_value=json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "确认来源未承接"):
            self.run_revision(good, runner)
        self.assertEqual(runner.call_count, 3)

    def test_confirmation_can_move_to_an_unresolved_question(self):
        current = self.artifact()
        output = deepcopy(current)
        removed = output["extractedFacts"].pop()
        output["questions"][0]["sourceReferences"].append(removed["fact"]["sourceReferences"][0])
        runner = Mock(return_value=json.dumps(output))
        self.run_revision(current, runner)
        self.assertEqual(runner.call_count, 1)
