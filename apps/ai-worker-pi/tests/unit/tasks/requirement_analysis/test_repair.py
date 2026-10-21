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

FIXTURES = Path(__file__).resolve().parents[4] / "tests/fixtures/requirement_artifacts"


def example(kind):
    return json.loads((FIXTURES / f"{kind}.example.json").read_text())


class RepairTests(unittest.TestCase):
    def execute(self, root, stage, runner, progress, *, revision=False, richtext=False):
        config = {}
        if stage == "feature_understanding":
            config["firstStepOutput"] = example("document-extraction")
        if revision:
            config["revisionInstruction"] = "只修订已确认的入口说明"
            config["firstStepOutput" if stage == "extracting_text" else "resultYaml"] = example(
                "document-extraction" if stage == "extracting_text" else "requirement-understanding"
            )
        task = Task(
            task_id="task",
            run_id="run",
            task_type="requirement_analysis",
            checkpoint_enabled=True,
            current_stage=stage,
            config_json=json.dumps(config),
            payload=TaskPayload(
                openapi_content="", document_type="richtext" if richtext else "word"
            ),
        )
        return execute_two_stage(
            task=task,
            started_at=datetime.now().astimezone(),
            progress_callback=progress.append,
            config_path=None,
            workspace=Path(root),
            skill_runner=runner,
            source_downloader=SimpleNamespace(
                download_source=lambda **kw: Path(root) / "source.html",
                download_images=lambda **kw: [
                    {"fileId": "img", "sourcePath": str(Path(root) / "img.png")}
                ],
            ),
            first_skill_name="extract-richtext-enhanced-text"
            if richtext
            else "extract-docx-enhanced-text",
            second_skill_name="prd-feature-understanding-skill",
        )

    def test_both_stages_repair_and_preserve_materials_and_revision(self):
        for stage, kind in (
            ("extracting_text", "document-extraction"),
            ("feature_understanding", "requirement-understanding"),
        ):
            for revision in (False, True):
                with (
                    self.subTest(stage=stage, revision=revision),
                    tempfile.TemporaryDirectory() as root,
                ):
                    good = example(kind)
                    bad = deepcopy(good)
                    bad["questions"][0]["affectedRefs"][0]["id"] = "missing"
                    runner = Mock(side_effect=[json.dumps(bad), json.dumps(good)])
                    progress = []
                    result = self.execute(
                        root, stage, runner, progress, revision=revision, richtext=True
                    )
                    self.assertEqual(runner.call_count, 2)
                    first, second = [call.kwargs for call in runner.call_args_list]
                    self.assertEqual(first["input_text"], second["input_text"])
                    self.assertEqual(first.get("media"), second.get("media"))
                    self.assertIn("affectedRefs", second["extra_instruction"])
                    self.assertIn("missing", second["extra_instruction"])
                    events = [
                        json.loads(p.result_summary_json)["outputValidation"]
                        for p in progress
                        if p.stage_status == "running"
                    ]
                    self.assertEqual(events[-1]["repairAttempt"], 1)
                    repairing = next(p for p in progress if p.stage_status == "running")
                    saved = json.loads(repairing.intermediate_json_text)
                    if stage == "feature_understanding":
                        self.assertEqual(saved["firstStepOutput"], example("document-extraction"))
                    if revision:
                        self.assertEqual(saved["revisionInstruction"], "只修订已确认的入口说明")
                        if stage == "feature_understanding":
                            self.assertEqual(json.loads(repairing.output_yaml), good)

                    if stage == "extracting_text":
                        self.assertIsNone(result)
                        self.assertEqual(progress[-1].stage_status, "waiting_review")
                    else:
                        self.assertEqual(json.loads(result.output_yaml), good)
                    records = list(Path(root).rglob("attempt-*.json"))
                    self.assertEqual(len(records), 2)

    def test_native_compact_output_repairs_evidence_without_expanding_storage(self):
        with tempfile.TemporaryDirectory() as root:
            good = example("requirement-understanding")
            bad = deepcopy(good)
            bad["modules"][0]["purpose"]["evidenceIds"] = ["missing"]
            runner = Mock(side_effect=[json.dumps(bad), json.dumps(good)])
            result = self.execute(root, "feature_understanding", runner, [])
            self.assertEqual(json.loads(result.output_yaml), good)
            self.assertEqual(runner.call_count, 2)
            instruction = runner.call_args_list[0].kwargs["extra_instruction"]
            self.assertIn('"const": "2.0"', instruction)
            self.assertIn("conditionRuleIds", instruction)

    def test_old_version_requires_model_correction_instead_of_automatic_conversion(self):
        with tempfile.TemporaryDirectory() as root:
            current = example("requirement-understanding")
            old = {**current, "schemaVersion": "1.0"}
            runner = Mock(side_effect=[json.dumps(old), json.dumps(current)])
            result = self.execute(root, "feature_understanding", runner, [])
            self.assertEqual(runner.call_count, 2)
            self.assertIn("schemaVersion", runner.call_args_list[1].kwargs["extra_instruction"])
            self.assertEqual(json.loads(result.output_yaml), current)

    def test_exhaustion_never_publishes_invalid_output(self):
        with tempfile.TemporaryDirectory() as root:
            runner, progress = Mock(return_value="{}"), []
            with self.assertRaisesRegex(ValueError, "3 次"):
                self.execute(root, "extracting_text", runner, progress)
            self.assertEqual(runner.call_count, 3)
            self.assertTrue(
                all(
                    json.loads(p.intermediate_json_text) == {} and not p.output_yaml
                    for p in progress
                )
            )
            self.assertTrue(all(p.stage_status == "running" for p in progress))

    def test_model_errors_and_truncation_do_not_trigger_repairs(self):
        for result in (
            RuntimeError("transport"),
            SimpleNamespace(content="{}", error="auth error"),
            SimpleNamespace(content="{}", finish_reason="length"),
        ):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as root:
                runner = (
                    Mock(side_effect=result)
                    if isinstance(result, Exception)
                    else Mock(return_value=result)
                )
                with self.assertRaises((ValueError, RuntimeError)):
                    self.execute(root, "extracting_text", runner, [])
                self.assertEqual(runner.call_count, 1)

    def test_async_runner_repairs_invalid_json(self):
        calls = []

        async def runner(**kwargs):
            calls.append(kwargs)
            return "not json" if len(calls) == 1 else json.dumps(example("document-extraction"))

        with tempfile.TemporaryDirectory() as root:
            self.execute(root, "extracting_text", runner, [])
        self.assertEqual(len(calls), 2)

    def test_second_repair_can_succeed_without_resolving_business_questions(self):
        good = example("document-extraction")
        runner = Mock(side_effect=["not json", "{}", json.dumps(good)])
        progress = []
        with tempfile.TemporaryDirectory() as root:
            self.execute(root, "extracting_text", runner, progress)
            records = list(Path(root).rglob("attempt-*.json"))
            self.assertEqual(len(records), 3)
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in records))
        self.assertEqual(runner.call_count, 3)
        actual = json.loads(progress[-1].intermediate_json_text)["firstStepOutput"]
        self.assertEqual(actual["questions"], good["questions"])

    def test_invalid_upstream_is_not_sent_to_model_for_repair(self):
        from unittest.mock import patch

        runner = Mock()
        with tempfile.TemporaryDirectory() as root:
            with patch(__name__ + ".example", return_value={}):
                with self.assertRaises(ValueError):
                    self.execute(root, "feature_understanding", runner, [])
        runner.assert_not_called()
