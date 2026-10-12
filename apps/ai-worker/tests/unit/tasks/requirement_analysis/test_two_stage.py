import json
import sys
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.platform.skills import required_skills
from testing_agent_ai_worker.requirement_artifacts import validate_artifact
from testing_agent_ai_worker.tasks.requirement_analysis.two_stage import execute_two_stage

FIXTURES = Path(__file__).resolve().parents[4] / "tests/fixtures/requirement_artifacts"


def example(name):
    return json.loads((FIXTURES / (name + ".example.json")).read_text())


class TwoStageTests(unittest.TestCase):
    def task(self, stage, config=None):
        return Task(
            task_id="worker",
            run_id="run",
            task_type="requirement_analysis",
            checkpoint_enabled=True,
            current_stage=stage,
            config_json=json.dumps(config or {}),
            payload=TaskPayload(
                openapi_content="",
                source_content="原材料",
                document_type="word",
                metadata={"workflowVersion": 2},
            ),
        )

    def run_stage(self, task, runner, progress):
        return execute_two_stage(
            task=task,
            started_at=datetime.now().astimezone(),
            progress_callback=progress.append,
            config_path=None,
            workspace=Path("/tmp"),
            skill_runner=runner,
            source_downloader=SimpleNamespace(
                download_source=lambda **kwargs: Path("/tmp/source.txt")
            ),
            first_skill_name="extract-docx-enhanced-text",
            second_skill_name="prd-feature-understanding-skill",
        )

    def test_extraction_pauses_for_review_and_saves_an_object(self):
        task, progress = self.task("extracting_text"), []
        result = self.run_stage(
            task, lambda **kwargs: json.dumps(example("document-extraction")), progress
        )
        self.assertIsNone(result)
        self.assertEqual(progress[0].stage_status, "waiting_review")
        config = json.loads(progress[0].intermediate_json_text)
        self.assertEqual(config["firstStepOutput"], example("document-extraction"))
        self.assertNotIn("secondStepOutput", config)

    def test_understanding_retry_and_revision_receive_complete_upstream(self):
        extraction, understanding = (
            example("document-extraction"),
            example("requirement-understanding"),
        )
        for revision in (False, True):
            with self.subTest(revision=revision):
                config = {"firstStepOutput": extraction}
                if revision:
                    config.update(
                        resultYaml=json.dumps(understanding), revisionInstruction="确认筛选操作范围"
                    )
                captured = []

                def runner(**kwargs):
                    captured.append(kwargs)
                    return json.dumps(understanding)

                result = self.run_stage(self.task("feature_understanding", config), runner, [])
                body = json.loads(captured[0]["input_text"])
                self.assertEqual(body["documentExtraction"], extraction)
                self.assertEqual(body["originalSourceContent"], "原材料")
                self.assertEqual(captured[0]["skill_name"], "prd-feature-understanding-skill")
                self.assertEqual(json.loads(result.output_yaml), understanding)
                if revision:
                    self.assertEqual(body["currentArtifact"], understanding)
                    self.assertEqual(body["currentArtifact"]["questions"][0]["status"], "open")

    def test_bad_generation_does_not_publish_artifact(self):
        progress = []
        with self.assertRaises(ValueError):
            self.run_stage(
                self.task("extracting_text"), lambda **kwargs: "```json\n{}\n```", progress
            )
        self.assertEqual(len(progress), 2)
        self.assertTrue(all(p.stage_status == "running" for p in progress))
        self.assertTrue(all(json.loads(p.intermediate_json_text) == {} for p in progress))

    def test_skill_selection_uses_only_two_reviewed_stages(self):
        task = self.task("feature_understanding")
        self.assertEqual(required_skills(task), ["prd-feature-understanding-skill"])
        task.current_stage = "extracting_text"
        self.assertEqual(required_skills(task), ["extract-docx-enhanced-text"])
        task.current_stage = "writing_requirement"
        with self.assertRaises(ValueError):
            required_skills(task)
        task.current_stage = "extracting_text"
        task.checkpoint_enabled = False
        with self.assertRaises(ValueError):
            required_skills(task)

    def test_source_and_business_reference_errors_are_rejected(self):
        for mutation in [
            lambda d: d["modules"][0]["purpose"].update(confirmationStatus="confirmed"),
            lambda d: d["businessFlows"][0]["steps"][0].update(operationId="missing"),
            lambda d: d["questions"][0]["affectedRefs"][0].update(id="missing"),
            lambda d: d["modules"][0]["operations"][0]["interaction"]["trigger"][
                "sourceReferences"
            ][0].update(sourceId="missing"),
        ]:
            document = deepcopy(example("requirement-understanding"))
            mutation(document)
            with self.assertRaises(ValueError):
                validate_artifact(document, "requirement_understanding")

    def test_table_bounds_and_hierarchy_cycles_are_rejected(self):
        for mutation in [
            lambda d: d["contentBlocks"][0].update(parentId="B03"),
            lambda d: d["contentBlocks"][2]["table"]["cells"][0].update(row=100),
        ]:
            document = deepcopy(example("document-extraction"))
            mutation(document)
            with self.assertRaises(ValueError):
                validate_artifact(document, "document_extraction")

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_artifact(
                '{"artifactType":"document_extraction","artifactType":"x"}', "document_extraction"
            )

    def test_revision_reads_old_answers_but_publishes_body_without_resolved_history(self):
        for stage, kind, field in [
            ("extracting_text", "document_extraction", "firstStepOutput"),
            ("feature_understanding", "requirement_understanding", "resultYaml"),
        ]:
            with self.subTest(stage=stage):
                current = example(kind.replace("_", "-"))
                current["sources"][0]["type"] = "user_confirmation"
                current["questions"][0].update(
                    status="resolved",
                    answer={
                        "value": "上游算子为 hoi_tool",
                        "confirmationStatus": "confirmed",
                        "sourceReferences": [
                            {
                                "sourceId": current["sources"][0]["id"],
                                "locator": "用户答复",
                                "excerpt": "上游算子为 hoi_tool",
                            }
                        ],
                        "relatedQuestionIds": [],
                    },
                )
                updated = deepcopy(current)
                updated["questions"] = updated["questions"][1:]

                def remove_question_reference(item):
                    if isinstance(item, dict):
                        if "relatedQuestionIds" in item:
                            item["relatedQuestionIds"] = [
                                q
                                for q in item["relatedQuestionIds"]
                                if q != current["questions"][0]["id"]
                            ]
                        for child in item.values():
                            remove_question_reference(child)
                    elif isinstance(item, list):
                        for child in item:
                            remove_question_reference(child)

                remove_question_reference(updated)
                target = (
                    updated["extractedFacts"][0]["fact"]
                    if stage == "extracting_text"
                    else updated["modules"][0]["operations"][0]["goal"]
                )
                target.update(current["questions"][0]["answer"])
                config = {
                    "firstStepOutput": example("document-extraction"),
                    field: current,
                    "revisionInstruction": "将已回答问题补入正文并删除已解决问题",
                }
                captured, progress = [], []

                def runner(**kwargs):
                    captured.append(kwargs)
                    return json.dumps(updated)

                result = self.run_stage(self.task(stage, config), runner, progress)
                body = json.loads(captured[0]["input_text"])
                self.assertEqual(
                    body["currentArtifact"]["questions"][0]["answer"]["value"],
                    "上游算子为 hoi_tool",
                )
                self.assertIn("已解决问题从 questions 删除", captured[0]["extra_instruction"])
                output = (
                    json.loads(progress[0].intermediate_json_text)["firstStepOutput"]
                    if stage == "extracting_text"
                    else json.loads(result.output_yaml)
                )
                self.assertFalse(any(q["status"] == "resolved" for q in output["questions"]))
                self.assertEqual(validate_artifact(output, kind), updated)
                with self.assertRaisesRegex(ValueError, "已解决问题"):
                    self.run_stage(
                        self.task(stage, config), lambda **kwargs: json.dumps(current), []
                    )
