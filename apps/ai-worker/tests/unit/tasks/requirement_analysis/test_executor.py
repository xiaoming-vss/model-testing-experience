import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from testing_agent_ai_worker.config.models import NanobotConfig
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.tasks.requirement_analysis.executor import (
    RequirementAnalysisNanobotExecutor,
)

FIXTURES = Path(__file__).resolve().parents[4] / "tests/fixtures/requirement_artifacts"


def artifact(name):
    return json.loads((FIXTURES / (name + ".example.json")).read_text())


class RequirementAnalysisExecutorTests(unittest.TestCase):
    def task(self, **updates):
        return Task(
            task_id="worker",
            run_id="run",
            task_type=updates.pop("task_type", "requirement_analysis"),
            project_id="project",
            requirement_id="requirement",
            checkpoint_enabled=True,
            current_stage=updates.pop("current_stage", "extracting_text"),
            config_json=json.dumps(updates.pop("config", {})),
            payload=TaskPayload(
                openapi_content="",
                document_type=updates.pop("document_type", "text"),
                document_download_url="/internal/ai-worker/tasks/worker/requirement-document",
                source_content="/v1/requirements/requirement/download",
                metadata={"workflowVersion": 2},
            ),
            **updates,
        )

    def executor(self, root, runner, downloads):
        def download(**kwargs):
            downloads.append(kwargs)
            return Path(root) / "source.txt"

        return RequirementAnalysisNanobotExecutor(
            nanobot_config=NanobotConfig(runtime_root=root),
            skill_runner=runner,
            source_downloader=SimpleNamespace(download_source=download),
        )

    def test_extraction_downloads_original_and_stops_for_review(self):
        calls, downloads, progress = [], [], []

        def runner(**kwargs):
            calls.append(kwargs)
            return json.dumps(artifact("document-extraction"))

        with tempfile.TemporaryDirectory() as root:
            executor = self.executor(root, runner, downloads)
            task = self.task(document_type="txt")
            result = executor.execute(task, datetime.now().astimezone(), progress.append)
        self.assertIsNone(result)
        self.assertEqual(task.payload.document_type, "text")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["skill_name"], "extract-docx-enhanced-text")
        self.assertEqual(downloads[0]["document_download_url"], task.payload.document_download_url)
        self.assertEqual(progress[0].stage_status, "waiting_review")
        self.assertEqual(
            json.loads(progress[0].intermediate_json_text)["firstStepOutput"],
            artifact("document-extraction"),
        )

    def test_understanding_reads_approved_json_without_redownloading(self):
        calls, downloads = [], []

        def runner(**kwargs):
            calls.append(kwargs)
            return json.dumps(artifact("requirement-understanding"))

        with tempfile.TemporaryDirectory() as root:
            executor = self.executor(root, runner, downloads)
            result = executor.execute(
                self.task(
                    current_stage="feature_understanding",
                    config={"firstStepOutput": artifact("document-extraction")},
                ),
                datetime.now().astimezone(),
                lambda _: None,
            )
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(downloads, [])
        self.assertEqual(calls[0]["skill_name"], "prd-feature-understanding-skill")
        self.assertEqual(
            json.loads(calls[0]["input_text"])["documentExtraction"],
            artifact("document-extraction"),
        )

    def test_wrong_task_and_unsupported_document_fail_before_model(self):
        def runner(**kwargs):
            self.fail("unexpected model call")

        with tempfile.TemporaryDirectory() as root:
            executor = self.executor(root, runner, [])
            for task in [self.task(task_type="api_case_generate"), self.task(document_type="pdf")]:
                result = executor.execute(task, datetime.now().astimezone(), lambda _: None)
                self.assertEqual(result.status, TaskStatus.FAILED)

    def test_unknown_stage_and_disabled_review_cannot_run(self):
        with tempfile.TemporaryDirectory() as root:
            executor = self.executor(root, lambda **kw: self.fail("unexpected model call"), [])
            task = self.task(current_stage="writing_requirement")
            with self.assertRaises(ValueError):
                executor.execute(task, datetime.now().astimezone(), lambda _: None)
            task.current_stage = "extracting_text"
            task.checkpoint_enabled = False
            with self.assertRaises(ValueError):
                executor.execute(task, datetime.now().astimezone(), lambda _: None)
