import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import yaml

from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.platform.skills import required_skills
from tests.unit.tasks.ui_case_generate import test_executor

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/ui_generation"


def read(name):
    return json.loads((FIXTURES / (name + ".json")).read_text())


class ThreeStageTests(unittest.TestCase):
    def execute(self, root, stage, config, response, revision=False):
        task = test_executor.UiCaseExecutorTests()._task()
        task.checkpoint_enabled = True
        task.current_stage = stage
        task.payload.metadata.update(
            uiWorkflowVersion="ui_three_stage/1.0", functionalCases=read("cases")
        )
        task.config_json = json.dumps(config, ensure_ascii=False)
        runner = (
            Mock(side_effect=response)
            if isinstance(response, list) or callable(response)
            else Mock(return_value=response)
        )
        source = Path(root) / "source"
        source.mkdir(exist_ok=True)
        (source / "page.vue").write_text("<div>甲</div>")
        from datetime import datetime

        from testing_agent_ai_worker.config.models import PiConfig
        from testing_agent_ai_worker.tasks.ui_case_generate.executor import UiCaseExecutor

        executor = UiCaseExecutor(
            agent_config=PiConfig(runtime_root=root),
            repository_source_preparer=test_executor.FakeRepositoryPreparer(Path(root) / "run"),
            credentials_fetcher=lambda task: ["credential"],
            skill_runner=runner,
        )
        progress = []
        result = executor.execute(task, datetime.now().astimezone(), progress.append)
        return task, result, runner, progress

    def test_surface_stops_for_review_and_calls_only_one_skill(self):
        with tempfile.TemporaryDirectory() as root:
            task, result, runner, progress = self.execute(
                root, "ui_surface", {}, json.dumps(read("surface"))
            )
        self.assertIsNone(result)
        self.assertEqual(required_skills(task), ["mtx-extract-ui-test-surface"])
        runner.assert_called_once()
        self.assertEqual(progress[-1].stage_status, "waiting_review")
        self.assertEqual(
            json.loads(progress[-1].intermediate_json_text)["uiSurface"], read("surface")
        )

    def test_design_does_not_require_confirmed_locators(self):
        with tempfile.TemporaryDirectory() as root:
            task, result, runner, progress = self.execute(
                root, "ui_design", {"uiSurface": read("surface")}, json.dumps(read("design"))
            )
        self.assertIsNone(result)
        self.assertEqual(required_skills(task), ["mtx-map-functional-cases-to-ui-scenarios"])
        self.assertEqual(
            runner.call_args.kwargs["skill_name"], "mtx-map-functional-cases-to-ui-scenarios"
        )
        body = json.loads(runner.call_args.kwargs["input_text"].split("\n用户生成指令：")[0])
        self.assertEqual(body["functionalCases"], read("cases"))
        self.assertEqual(body["surface"], read("surface"))
        self.assertIn("absent", body["capabilities"]["assertions"])
        self.assertEqual(
            json.loads(progress[-1].intermediate_json_text)["uiDesign"], read("design")
        )

    def test_yaml_preserves_missing_fields_and_confirmed_inputs(self):
        config = {"uiSurface": read("surface"), "uiDesign": read("design")}
        raw = (FIXTURES / "draft.yaml").read_text()
        with tempfile.TemporaryDirectory() as root:
            task, result, runner, progress = self.execute(
                root, "ui_yaml", config, [raw, '{"issues": []}']
            )
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(yaml.safe_load(result.output_yaml), yaml.safe_load(raw))
        intermediate = json.loads(result.intermediate_json_text)
        self.assertEqual(intermediate.pop("sourceKind"), "repository")
        self.assertEqual(intermediate.pop("sourceCommit"), "a1b2c3d")
        self.assertEqual(intermediate.pop("sourceRepository")["repositoryId"], "repo-1")
        self.assertEqual(intermediate, config)
        self.assertEqual(required_skills(task), ["mtx-generate-ui-test-case"])
        self.assertEqual(runner.call_count, 2)
        self.assertIn(":ui-yaml-review:", runner.call_args.kwargs["session_key"])

    def test_yaml_review_failure_returns_success_with_incomplete_report(self):
        config = {"uiSurface": read("surface"), "uiDesign": read("design")}
        raw = (FIXTURES / "draft.yaml").read_text()
        with tempfile.TemporaryDirectory() as root:
            _, result, runner, _ = self.execute(
                root, "ui_yaml", config, [raw, RuntimeError("provider failure")]
            )
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(yaml.safe_load(result.output_yaml), yaml.safe_load(raw))
        self.assertEqual(
            json.loads(result.result_summary_json)["uiSemanticReview"]["status"], "incomplete"
        )

    def test_revision_only_changes_current_stage(self):
        config = {
            "uiSurface": read("surface"),
            "uiDesign": read("design"),
            "revisionInstruction": "增加显示检查",
        }
        raw = json.dumps(read("design"))
        with tempfile.TemporaryDirectory() as root:
            task, result, runner, progress = self.execute(root, "ui_design", config, raw)
        body = json.loads(runner.call_args.kwargs["input_text"].split("\n用户生成指令：")[0])
        self.assertEqual(body["currentArtifact"], read("design"))
        self.assertEqual(body["revisionInstruction"], "增加显示检查")
        self.assertNotIn("revisionInstruction", json.loads(progress[-1].intermediate_json_text))

    def test_invalid_design_fails_without_publishing(self):
        bad = read("design")
        bad["cases"][0]["preconditions"] = []
        with tempfile.TemporaryDirectory() as root:
            _, result, runner, progress = self.execute(
                root, "ui_design", {"uiSurface": read("surface")}, json.dumps(bad)
            )
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(runner.call_count, 3)
        self.assertFalse(any(p.stage_status == "waiting_review" for p in progress))

    def test_untrusted_artifact_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            _, result, runner, progress = self.execute(
                root,
                "ui_surface",
                {},
                json.dumps({"artifactPath": "/tmp/untrusted.json", "status": "written"}),
            )
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertFalse(any(p.stage_status == "waiting_review" for p in progress))

    def test_unimportable_yaml_is_repaired_before_completion(self):
        import yaml

        config = {"uiSurface": read("surface"), "uiDesign": read("design")}
        raw = (FIXTURES / "draft.yaml").read_text()
        bad = yaml.safe_load(raw)
        bad[0]["stepsJson"][0]["unsupportedExtraction"] = {"saveAs": "record"}
        with tempfile.TemporaryDirectory() as root:
            _, result, runner, _ = self.execute(
                root, "ui_yaml", config, [yaml.safe_dump(bad), raw, '{"issues": []}']
            )
        self.assertEqual(runner.call_count, 3)
        sessions = [call.kwargs["session_key"] for call in runner.call_args_list]
        self.assertEqual(len(set(sessions)), 3)
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(yaml.safe_load(result.output_yaml), yaml.safe_load(raw))

    def test_fixed_path_symlink_is_not_followed(self):
        def generate(**kwargs):
            inputs, _ = json.JSONDecoder().raw_decode(kwargs["input_text"])
            path = Path(inputs["outputPath"])
            other = path.parent / "untrusted.json"
            other.write_text(json.dumps(read("surface")), encoding="utf-8")
            path.unlink(missing_ok=True)
            path.symlink_to(other)
            return "已写入"

        with tempfile.TemporaryDirectory() as root:
            _, result, _, progress = self.execute(root, "ui_surface", {}, generate)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertFalse(any(p.stage_status == "waiting_review" for p in progress))

    def test_direct_design_json_code_block_is_accepted(self):
        raw = "```json\n" + json.dumps(read("design")) + "\n```"
        with tempfile.TemporaryDirectory() as root:
            _, result, runner, progress = self.execute(
                root, "ui_design", {"uiSurface": read("surface")}, raw
            )
        self.assertIsNone(result)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(progress[-1].stage_status, "waiting_review")

    def test_design_schema_and_exact_source_feedback_survive_repair(self):
        bad = read("design")
        bad["cases"][0]["steps"][0]["expectations"][0]["sourceQuote"] = "擅自改写预期"
        with tempfile.TemporaryDirectory() as root:
            _, result, runner, progress = self.execute(
                root,
                "ui_design",
                {"uiSurface": read("surface")},
                [json.dumps(bad), json.dumps(read("design"))],
            )
        self.assertIsNone(result)
        self.assertEqual(runner.call_count, 2)
        for call in runner.call_args_list:
            self.assertIn('"$defs"', call.kwargs["extra_instruction"])
            self.assertIn('"sourceQuote"', call.kwargs["extra_instruction"])
        repair = runner.call_args.kwargs["input_text"]
        self.assertIn("$.cases[0].steps[0].expectations[0].sourceQuote", repair)
        self.assertIn("source_quote_changed", repair)
        self.assertIn("擅自改写预期", repair)
        self.assertEqual(progress[-1].stage_status, "waiting_review")

    def test_invalid_json_duplicate_and_nonfinite_values_are_rejected(self):
        from testing_agent_ai_worker.tasks.ui_case_generate.chain import read_stage_json

        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve() / "artifact.json"
            for raw in ('{"cases": [], "cases": []}', '{"value": NaN}', '{"value": Infinity}'):
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    read_stage_json(raw, path)

    def test_wrong_field_type_has_path_and_is_bounded_without_publishing(self):
        bad = read("design")
        bad["cases"][0]["steps"][0]["actions"][0]["target"] = ["不能是数组"]
        with tempfile.TemporaryDirectory() as root:
            _, result, runner, progress = self.execute(
                root, "ui_design", {"uiSurface": read("surface")}, json.dumps(bad)
            )
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(runner.call_count, 3)
        repair = runner.call_args.kwargs["input_text"]
        self.assertIn("$.cases[0].steps[0].actions[0].target", repair)
        self.assertIn("string_type", repair)
        self.assertFalse(any(p.stage_status == "waiting_review" for p in progress))

    def test_repair_does_not_change_upstream_artifact_or_frozen_cases(self):
        bad = read("design")
        bad["cases"] = []
        with tempfile.TemporaryDirectory() as root:
            _, result, runner, progress = self.execute(
                root,
                "ui_design",
                {"uiSurface": read("surface")},
                [json.dumps(bad), json.dumps(read("design"))],
            )
        self.assertIsNone(result)
        for call in runner.call_args_list:
            inputs, _ = json.JSONDecoder().raw_decode(call.kwargs["input_text"])
            self.assertEqual(inputs["functionalCases"], read("cases"))
            self.assertEqual(inputs["surface"], read("surface"))
        self.assertEqual(
            json.loads(progress[-1].intermediate_json_text)["uiSurface"], read("surface")
        )

    def test_design_uses_response_and_ignores_workspace_artifact(self):
        def generate(**kwargs):
            body, _ = json.JSONDecoder().raw_decode(kwargs["input_text"])
            self.assertNotIn("outputPath", body)
            path = Path(kwargs["workspace"]) / "outputs" / "ui_design.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("invalid stale file")
            return json.dumps(read("design"))

        with tempfile.TemporaryDirectory() as root:
            _, result, runner, progress = self.execute(
                root, "ui_design", {"uiSurface": read("surface")}, generate
            )
        self.assertIsNone(result)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(progress[-1].stage_status, "waiting_review")
