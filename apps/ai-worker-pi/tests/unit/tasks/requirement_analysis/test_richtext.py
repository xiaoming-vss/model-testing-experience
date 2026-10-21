import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from testing_agent_ai_worker_pi.config.models import PiConfig
from testing_agent_ai_worker_pi.models.task import Task, TaskPayload
from testing_agent_ai_worker_pi.platform.skills import required_skills
from testing_agent_ai_worker_pi.tasks.requirement_analysis.executor import (
    RequirementAnalysisPiExecutor,
)
from testing_agent_ai_worker_pi.tasks.requirement_analysis.skill import run_skill_step
from testing_agent_ai_worker_pi.tasks.requirement_analysis.source_downloader import (
    PlatformRequirementSourceDownloader,
)

FIXTURE = Path(__file__).resolve().parents[4] / "tests/fixtures/requirement_artifacts"


class RichtextTests(unittest.TestCase):
    def task(self, document_type="richtext"):
        return Task(
            task_id="task",
            run_id="run",
            task_type="requirement_analysis",
            checkpoint_enabled=True,
            current_stage="extracting_text",
            payload=TaskPayload(
                openapi_content="",
                document_type=document_type,
                document_download_url="/internal/ai-worker/tasks/task/requirement-document",
            ),
        )

    def test_routing_and_retired_txt(self):
        for kind, skill in (
            ("docx", "extract-docx-enhanced-text"),
            ("word", "extract-docx-enhanced-text"),
            ("richtext", "extract-richtext-enhanced-text"),
        ):
            self.assertEqual(required_skills(self.task(kind)), [skill])
        for kind in ("txt", "text"):
            with self.assertRaisesRegex(ValueError, "Word/DOCX"):
                required_skills(self.task(kind))
        task = self.task("text")
        task.current_stage = "feature_understanding"
        self.assertEqual(required_skills(task), ["prd-feature-understanding-skill"])

    def test_html_images_reach_model_and_keep_original_positions(self):
        html = b'<p>## Title</p><img data-file-id="img-1"><p>after</p><img data-file-id="img-1">'
        png = b"\x89PNG\r\n\x1a\nfixture"
        paths, calls, progress = [], [], []

        def get(path):
            paths.append(path)
            return png if "requirement-images" in path else html

        def runner(**kwargs):
            calls.append(kwargs)
            body = json.loads(kwargs["input_text"])
            self.assertEqual(Path(body["sourcePath"]).suffix, ".html")
            self.assertEqual(Path(body["sourcePath"]).read_bytes(), html)
            self.assertEqual(len(body["images"]), 1)
            self.assertEqual(body["images"][0]["fileId"], "img-1")
            self.assertEqual(Path(kwargs["media"][0]).read_bytes(), png)
            return (FIXTURE / "document-extraction.example.json").read_text()

        with tempfile.TemporaryDirectory() as root:
            executor = RequirementAnalysisPiExecutor(
                pi_config=PiConfig(runtime_root=root),
                skill_runner=runner,
                source_downloader=PlatformRequirementSourceDownloader(
                    SimpleNamespace(get_signed_file_bytes=get), "worker"
                ),
            )
            self.assertIsNone(
                executor.execute(self.task(), datetime.now().astimezone(), progress.append)
            )
        self.assertEqual(calls[0]["skill_name"], "extract-richtext-enhanced-text")
        self.assertEqual(progress[0].stage_status, "waiting_review")
        self.assertEqual(
            paths[-1], "/internal/ai-worker/tasks/task/requirement-images/img-1?workerId=worker"
        )
        self.assertEqual(len(paths), 2)

    def test_bad_image_reference_and_download_failure_stop_before_model(self):
        for html in ('<img data-file-id="../secret">', '<img data-file-id="img-1">'):
            with self.subTest(html=html), tempfile.TemporaryDirectory() as root:
                source = Path(root) / "source.html"
                source.write_text(html)
                downloader = PlatformRequirementSourceDownloader(
                    SimpleNamespace(get_signed_file_bytes=lambda _: b"not an image"), "worker"
                )
                with self.assertRaises(ValueError):
                    downloader.download_images(source=source, task=self.task())


class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_receives_media(self):
        calls = []

        class Bot:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def run(self, message, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(content="{}")

        await run_skill_step(
            input_text="{}",
            session_key="run",
            skill_name="extract-richtext-enhanced-text",
            media=["/tmp/image.png"],
            from_config=lambda **kwargs: Bot(),
        )
        self.assertEqual(calls[0]["media"], ["/tmp/image.png"])
