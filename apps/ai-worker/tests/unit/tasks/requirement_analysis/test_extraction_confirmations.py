import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.tasks.requirement_analysis.material_stage import execute_material_stage

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "tests/fixtures/requirement_artifacts/readable-material.example.json"
)


class ExtractionConfirmationTests(unittest.TestCase):
    def artifact(self):
        value = json.loads(FIXTURE.read_text())
        value["sources"].append(
            {"id": "CONFIRM", "type": "user_confirmation", "name": "业务确认", "location": None}
        )
        value["materialBlocks"].append(
            {
                "id": "BC",
                "sourceId": "CONFIRM",
                "parentId": None,
                "kind": "paragraph",
                "locator": "答复A",
                "content": {"text": "只允许项目成员提交"},
            }
        )
        value["functions"][0]["sections"][0]["items"].append(
            {"text": "只允许项目成员提交", "status": "confirmed", "materialBlockIds": ["BC"]}
        )
        return value

    def run_revision(self, current, runner):
        task = Task(
            task_id="extraction",
            attempt_id="local",
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
            result = execute_material_stage(
                task=task,
                started_at=datetime.now().astimezone(),
                progress_callback=progress.append,
                config_path=None,
                workspace=Path(work),
                skill_runner=runner,
                source_downloader=SimpleNamespace(
                    download_source=lambda **kwargs: Path(work) / "source.docx"
                ),
                first_skill_name="mtx-organize-requirement-material",
            )
        return result

    def test_missing_confirmation_is_repaired_before_review(self):
        good = self.artifact()
        bad = deepcopy(good)
        bad["functions"][0]["sections"][0]["items"].pop()
        runner = Mock(side_effect=[json.dumps(bad), json.dumps(good)])
        result = self.run_revision(good, runner)
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(json.loads(result.output_yaml), good)
        body = json.loads(runner.call_args_list[0].kwargs["input_text"])
        self.assertEqual(body["confirmationReferences"][0]["locator"], "答复A")

    def test_confirmation_only_in_material_does_not_pass(self):
        good = self.artifact()
        bad = deepcopy(good)
        bad["functions"][0]["sections"][0]["items"].pop()
        runner = Mock(return_value=json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "确认来源未承接"):
            self.run_revision(good, runner)
        self.assertEqual(runner.call_count, 3)

    def test_confirmation_can_move_to_an_unresolved_question(self):
        current = self.artifact()
        output = deepcopy(current)
        output["functions"][0]["sections"][0]["items"].pop()
        output["questions"].append(
            {
                "id": "Q1",
                "question": "谁可以提交？",
                "reason": "部分答复存在歧义",
                "materialBlockIds": ["BC"],
                "functionIds": ["F1"],
            }
        )
        runner = Mock(return_value=json.dumps(output))
        self.run_revision(current, runner)
        self.assertEqual(runner.call_count, 1)
