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
from testing_agent_ai_worker.tasks.requirement_analysis.material_stage import execute_material_stage

FIXTURES = Path(__file__).resolve().parents[4] / "tests/fixtures/requirement_artifacts"


def example(name):
    return json.loads((FIXTURES / (name + ".example.json")).read_text())


class TwoStageTests(unittest.TestCase):
    def task(self, stage, config=None):
        return Task(
            task_id="worker",
            attempt_id="run",
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

    def run_stage(self, task, runner, progress, attachment_downloader=None):
        return execute_material_stage(
            task=task,
            started_at=datetime.now().astimezone(),
            progress_callback=progress.append,
            config_path=None,
            workspace=Path("/tmp"),
            skill_runner=runner,
            source_downloader=SimpleNamespace(
                download_source=lambda **kwargs: Path("/tmp/source.txt")
            ),
            attachment_downloader=attachment_downloader,
            first_skill_name="mtx-organize-requirement-material",
        )

    def test_extraction_pauses_for_review_and_saves_an_object(self):
        task, progress = self.task("extracting_text"), []
        result = self.run_stage(
            task, lambda **kwargs: json.dumps(example("readable-material")), progress
        )
        self.assertEqual(result.status.value, "success")
        self.assertEqual(
            json.loads(result.output_yaml),
            example("readable-material"),
        )

    def test_new_material_cannot_run_unadapted_understanding(self):
        task = self.task("feature_understanding", {"firstStepOutput": example("readable-material")})
        with self.assertRaisesRegex(ValueError, "不支持阶段"):
            self.run_stage(task, lambda **kwargs: self.fail("unexpected model call"), [])

    def test_revision_attachments_are_downloaded_and_sent_as_media(self):
        extraction = example("readable-material")
        downloads, captured = [], []

        class Downloader:
            def download(self, *, task_id, workspace, attachments):
                downloads.append((task_id, attachments))
                return [
                    {
                        "fileId": "image-1",
                        "filename": "login.png",
                        "sourcePath": "/tmp/image.png",
                        "sourceLocation": "/v1/files/image-1/download",
                    }
                ]

        def runner(**kwargs):
            captured.append(kwargs)
            return json.dumps(extraction)

        task = self.task(
            "extracting_text",
            {
                "firstStepOutput": extraction,
                "revisionInstruction": "按截图补充",
                "revisionAttachments": [{"fileId": "image-1", "filename": "login.png"}],
            },
        )
        self.run_stage(task, runner, [], attachment_downloader=Downloader())
        self.assertEqual(downloads[0][0], "worker")
        self.assertEqual(captured[0]["media"], ["/tmp/image.png"])
        self.assertEqual(
            json.loads(captured[0]["input_text"])["revisionAttachments"],
            [{"fileId": "image-1", "filename": "login.png"}],
        )

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
        with self.assertRaises(ValueError):
            required_skills(task)
        task.current_stage = "extracting_text"
        self.assertEqual(required_skills(task), ["mtx-organize-requirement-material"])
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
            lambda d: d["evidence"][0].update(sourceId="missing"),
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

    def test_old_extraction_contract_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_artifact(example("document-extraction"), "document_extraction")
