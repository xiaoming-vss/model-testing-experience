import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.tasks.requirement_analysis.review_stage import (
    execute_review_stage,
)

FIXTURES = Path(__file__).resolve().parents[4] / "tests/fixtures/requirement_review"


def example(name):
    return json.loads((FIXTURES / f"{name}.example.json").read_text())


class ReviewStageTests(unittest.TestCase):
    def task(self, *, config=None, document_type="word", metadata=None):
        return Task(
            task_id="worker",
            attempt_id="run",
            task_type="requirement_analysis",
            checkpoint_enabled=True,
            current_stage="requirement_review",
            config_json=json.dumps(config or {}),
            payload=TaskPayload(
                openapi_content="",
                source_content="原材料",
                document_type=document_type,
                document_download_url="/internal/ai-worker/tasks/worker/requirement-document",
                metadata={
                    "workflowVersion": 2,
                    "documentFilename": "prd.docx",
                    "documentFileId": "file-1",
                    **(metadata or {}),
                },
            ),
        )

    def run_stage(self, task, runner, progress, *, workspace, downloader=None, attachments=None):
        source_downloader = downloader or SimpleNamespace(
            download_source=lambda **kwargs: Path(workspace) / "source.docx",
            download_images=lambda **kwargs: [],
        )
        return execute_review_stage(
            task=task,
            started_at=datetime.now().astimezone(),
            progress_callback=progress.append,
            config_path=None,
            workspace=Path(workspace),
            skill_runner=runner,
            source_downloader=source_downloader,
            attachment_downloader=attachments,
        )

    def test_initial_review_stops_for_manual_review_and_returns_none(self):
        calls, progress = [], []
        with tempfile.TemporaryDirectory() as root:
            result = self.run_stage(
                self.task(),
                lambda **kwargs: calls.append(kwargs) or json.dumps(example("blocked")),
                progress,
                workspace=root,
            )
        self.assertIsNone(result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["skill_name"], "mtx-review-requirement")
        body = json.loads(calls[0]["input_text"])
        self.assertEqual(body["documentType"], "word")
        self.assertEqual(body["sourceName"], "prd.docx")
        self.assertEqual(body["sourceLocation"], "/v1/files/file-1/download")
        self.assertNotIn("currentArtifact", body)
        self.assertNotIn("revisionInstruction", body)
        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0].current_stage, "requirement_review")
        self.assertEqual(progress[0].stage_status, "waiting_review")
        self.assertEqual(
            json.loads(progress[0].intermediate_json_text)["reviewOutput"],
            example("blocked"),
        )
        summary = json.loads(progress[0].result_summary_json)
        self.assertEqual(summary["reviewStatus"], "blocked")
        self.assertEqual(summary["blockerCount"], 1)
        self.assertEqual(summary["majorCount"], 0)

    def test_revision_sends_previous_artifact_and_instruction_only(self):
        calls = []
        previous = example("blocked")
        with tempfile.TemporaryDirectory() as root:
            self.run_stage(
                self.task(
                    config={
                        "reviewOutput": previous,
                        "revisionInstruction": "RR-01 已确认：库存不足不允许提交",
                    },
                ),
                lambda **kwargs: calls.append(kwargs) or json.dumps(example("passed")),
                [],
                workspace=root,
            )
        body = json.loads(calls[0]["input_text"])
        self.assertEqual(body["currentArtifact"], previous)
        self.assertEqual(body["revisionInstruction"], "RR-01 已确认：库存不足不允许提交")
        self.assertNotIn("referenceContext", body)

    def test_richtext_images_and_revision_attachments_reach_the_model(self):
        calls, downloads = [], []

        class Downloader:
            def download(self, *, task_id, workspace, attachments):
                downloads.append((task_id, attachments))
                return [
                    {
                        "fileId": "revision-image",
                        "filename": "clarify.png",
                        "sourcePath": "/tmp/clarify.png",
                        "sourceLocation": "/v1/files/revision-image/download",
                    }
                ]

        images = [
            {
                "fileId": "source-image",
                "sourcePath": "/tmp/source.png",
                "sourceLocation": "/v1/files/source-image/download",
            }
        ]
        downloader = SimpleNamespace(
            download_source=lambda **kwargs: Path("/tmp/source.html"),
            download_images=lambda **kwargs: images,
        )
        with tempfile.TemporaryDirectory() as root:
            self.run_stage(
                self.task(
                    document_type="richtext",
                    config={
                        "reviewOutput": example("blocked"),
                        "revisionInstruction": "按截图补充",
                        "revisionAttachments": [
                            {"fileId": "revision-image", "filename": "clarify.png"}
                        ],
                    },
                ),
                lambda **kwargs: calls.append(kwargs) or json.dumps(example("passed")),
                [],
                workspace=root,
                downloader=downloader,
                attachments=Downloader(),
            )
        self.assertEqual(calls[0]["media"], ["/tmp/source.png", "/tmp/clarify.png"])
        body = json.loads(calls[0]["input_text"])
        self.assertEqual(body["images"], images)
        self.assertEqual(
            body["revisionAttachments"],
            [{"fileId": "revision-image", "filename": "clarify.png"}],
        )
        self.assertEqual(downloads[0][0], "worker")

    def test_invalid_review_is_repaired_before_waiting_for_review(self):
        progress = []
        responses = ["{}", json.dumps(example("needs-clarification"))]
        with tempfile.TemporaryDirectory() as root:
            result = self.run_stage(
                self.task(),
                lambda **kwargs: responses.pop(0),
                progress,
                workspace=root,
            )
        self.assertIsNone(result)
        self.assertEqual([item.stage_status for item in progress], ["running", "waiting_review"])
        self.assertEqual(
            json.loads(progress[-1].intermediate_json_text)["reviewOutput"],
            example("needs-clarification"),
        )

    def test_file_receipt_uses_requirement_review_filename(self):
        calls, progress = [], []

        def runner(**kwargs):
            calls.append(kwargs)
            match = re.search(r"到以下绝对路径：\n([^\n]+)", kwargs["extra_instruction"])
            Path(match[1]).write_text(json.dumps(example("passed")), encoding="utf-8")
            return json.dumps({"artifactFile": "requirement-review.json"})

        with tempfile.TemporaryDirectory() as root:
            result = self.run_stage(self.task(), runner, progress, workspace=root)
        self.assertIsNone(result)
        self.assertEqual(len(calls), 1)
        self.assertIn('{"artifactFile":"requirement-review.json"}', calls[0]["extra_instruction"])
        self.assertEqual(
            json.loads(progress[-1].intermediate_json_text)["reviewOutput"],
            example("passed"),
        )

    def test_unknown_stage_and_disabled_review_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            task = self.task()
            task.current_stage = "extracting_text"
            with self.assertRaisesRegex(ValueError, "不支持阶段"):
                self.run_stage(task, lambda **kwargs: "{}", [], workspace=root)
            task = self.task()
            task.checkpoint_enabled = False
            with self.assertRaisesRegex(ValueError, "人工审核"):
                self.run_stage(task, lambda **kwargs: "{}", [], workspace=root)


if __name__ == "__main__":
    unittest.main()
