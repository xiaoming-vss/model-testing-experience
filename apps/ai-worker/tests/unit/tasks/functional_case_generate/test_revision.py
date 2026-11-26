import asyncio
import json
import unittest
from datetime import datetime
from types import SimpleNamespace

from testing_agent_ai_worker.config.models import PiConfig
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.tasks.functional_case_generate.detailed_batches import (
    run_functional_detailed_case_batches,
)
from testing_agent_ai_worker.tasks.functional_case_generate.executor import (
    FunctionalCaseExecutor,
)
from testing_agent_ai_worker.tasks.functional_case_generate.validation import (
    OutputValidationError,
)
from tests.unit.tasks.functional_case_generate.fixtures import (
    analysis,
    case,
    material,
    traceable_modules,
)


class FunctionalRevisionTests(unittest.TestCase):
    def task(self, stage, checkpoint=True):
        return Task(
            claim_id="claim",
            task_id="task",
            attempt_id="run",
            generate_task_id="generate",
            task_type="functional_case_generate",
            project_id="project",
            sprint_id="sprint",
            requirement_id="requirement",
            checkpoint_enabled=checkpoint,
            current_stage=stage,
            config_json=json.dumps(
                {
                    "requirementAnalysis": analysis(),
                    "caseNames": {"categories": [{"model": "login", "data": []}]},
                    "resultYaml": '{"cases":[{"case_module":"login","name":"existing case"}]}',
                    "revisionInstruction": "add error boundaries",
                }
            ),
            payload=TaskPayload(
                openapi_content="",
                source_content=json.dumps(material(), ensure_ascii=False),
                source_type="requirement",
                source_format="requirement_understanding_json",
                source_format_version="0.2",
            ),
        )

    def with_attachment(self, stage):
        task = self.task(stage)
        config = json.loads(task.config_json)
        config["revisionAttachments"] = [{"fileId": "image-1", "filename": "login.png"}]
        task.config_json = json.dumps(config)
        return task

    def downloader(self, downloads):
        class Downloader:
            def download(self, *, task_id, workspace, attachments):
                downloads.append((task_id, attachments))
                return [
                    {
                        "fileId": "image-1",
                        "filename": "login.png",
                        "sourcePath": "/tmp/revision-attachments/image-1.png",
                        "sourceLocation": "/v1/files/image-1/download",
                    }
                ]

        return Downloader()

    def test_checkpoint_revision_passes_images_as_media(self):
        downloads, calls = [], []

        def skill(**kwargs):
            calls.append(kwargs)
            return '{"updated":true}'

        executor = FunctionalCaseExecutor(
            agent_config=PiConfig(),
            skill_runner=skill,
            chain_runner=lambda **kwargs: self.fail("must not run full chain"),
            attachment_downloader=self.downloader(downloads),
        )
        executor.execute(
            self.with_attachment("requirement_analysis"),
            datetime.now().astimezone(),
            lambda _: None,
        )
        self.assertEqual(downloads[0][0], "task")
        self.assertEqual(calls[0]["media"], ["/tmp/revision-attachments/image-1.png"])
        self.assertIn("【本轮优化依据图片】", calls[0]["input_text"])
        self.assertIn("login.png", calls[0]["input_text"])

    def test_final_revision_passes_images_to_detailed_batches(self):
        downloads, calls = [], []

        def batches(**kwargs):
            calls.append(kwargs)
            return '{"cases":[{"name":"revised"}]}'

        executor = FunctionalCaseExecutor(
            agent_config=PiConfig(),
            detailed_batch_runner=batches,
            chain_runner=lambda **kwargs: self.fail("must not run full chain"),
            skill_runner=lambda **kwargs: self.fail("must not rerun upstream"),
            attachment_downloader=self.downloader(downloads),
        )
        executor.execute(
            self.with_attachment("detailed_cases"),
            datetime.now().astimezone(),
            lambda _: None,
        )
        self.assertEqual(calls[0]["media"], ["/tmp/revision-attachments/image-1.png"])
        self.assertIn("login.png", calls[0]["revision_instruction"])

    def test_checkpoint_revision_uses_current_output_and_clears_instruction(self):
        for stage, expected in [
            ("requirement_analysis", "test_scope_impact_risk"),
            ("case_names", "login"),
        ]:
            with self.subTest(stage=stage):
                calls, progress = [], []

                def skill(**kwargs):
                    calls.append(kwargs)
                    return '{"updated":true}'

                executor = FunctionalCaseExecutor(
                    agent_config=PiConfig(),
                    skill_runner=skill,
                    chain_runner=lambda **kwargs: self.fail("must not run full chain"),
                )
                result = executor.execute(
                    self.task(stage), datetime.now().astimezone(), progress.append
                )
                self.assertIsNone(result)
                self.assertIn(expected, calls[0]["input_text"])
                if stage == "case_names":
                    self.assertTrue(calls[0]["is_revision"])
                self.assertIn("readable_requirement_material", calls[0]["input_text"])
                self.assertIn("add error boundaries", calls[0]["input_text"])
                self.assertEqual(progress[0].stage_status, "waiting_review")
                self.assertEqual(progress[0].current_stage, stage)
                self.assertNotIn(
                    "revisionInstruction", json.loads(progress[0].intermediate_json_text)
                )

    def test_final_revision_dispatches_without_checkpoint_and_clears_instruction(self):
        for checkpoint in [False, True]:
            with self.subTest(checkpoint=checkpoint):
                calls = []

                def batches(**kwargs):
                    calls.append(kwargs)
                    return '{"cases":[{"name":"revised"}]}'

                executor = FunctionalCaseExecutor(
                    agent_config=PiConfig(),
                    detailed_batch_runner=batches,
                    chain_runner=lambda **kwargs: self.fail("must not run full chain"),
                    skill_runner=lambda **kwargs: self.fail("must not rerun upstream"),
                )
                result = executor.execute(
                    self.task("detailed_cases", checkpoint),
                    datetime.now().astimezone(),
                    lambda _: None,
                )
                self.assertIn("existing case", calls[0]["current_cases_json"])
                self.assertEqual(calls[0]["revision_instruction"], "add error boundaries")
                self.assertEqual(result.status, "success")
                self.assertNotIn("revisionInstruction", json.loads(result.intermediate_json_text))
                self.assertNotIn("resultYaml", json.loads(result.intermediate_json_text))
                self.assertIn("revised", result.output_yaml)

    def test_detailed_batches_receive_only_their_current_module(self):
        calls = []

        class Bot:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def run(self, message, **kwargs):
                calls.append(message)
                return SimpleNamespace(
                    content=json.dumps({"cases": [case(f"revised-{len(calls)}")]})
                )

        result = asyncio.run(
            run_functional_detailed_case_batches(
                requirement_analysis_json='{"purpose":"original"}',
                case_names_json=json.dumps(traceable_modules("login", "checkout")),
                session_key="session",
                skill_name="mtx-generate-solution-test-cases",
                current_cases_json=json.dumps(
                    {
                        "cases": [
                            {"case_module": "login", "name": "login-existing"},
                            {"module": "checkout", "name": "checkout-existing"},
                            {"module": "manually-added", "name": "manual-existing"},
                        ]
                    }
                ),
                revision_instruction="add errors",
                from_config=lambda **kwargs: Bot(),
            )
        )
        existing_cases = {"login-existing", "checkout-existing", "manual-existing"}
        for call in calls:
            present = {name for name in existing_cases if name in call}
            self.assertEqual(len(present), 1, call)
        self.assertTrue(all("add errors" in call for call in calls))
        self.assertEqual(len(json.loads(result)["cases"]), 3)

    def run_revision(self, answers):
        """Drive the real batch runner over two current cases; the model answers in order."""
        calls = []
        previous = [
            {"case_id": "case-a", **case("验证登录成功", "login")},
            {"case_id": "case-b", **case("验证登录失败", "login")},
        ]

        class Bot:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def run(self, message, **kwargs):
                calls.append(message)
                answer = answers[min(len(calls), len(answers)) - 1]
                return SimpleNamespace(content=json.dumps(answer, ensure_ascii=False))

        result = asyncio.run(
            run_functional_detailed_case_batches(
                requirement_analysis_json='{"purpose":"original"}',
                case_names_json=json.dumps(traceable_modules("login")),
                session_key="session",
                skill_name="mtx-generate-solution-test-cases",
                current_cases_json=json.dumps({"cases": previous}, ensure_ascii=False),
                revision_instruction="add errors",
                from_config=lambda **kwargs: Bot(),
            )
        )
        return json.loads(result)["cases"], calls, previous

    def test_revision_repairs_a_case_dropped_without_being_declared(self):
        cases, calls, previous = self.run_revision(
            [
                {"cases": [case("验证登录失败", "login")]},
                {"cases": [case("验证登录成功", "login"), case("验证登录失败", "login")]},
            ]
        )

        self.assertEqual(len(calls), 2)
        self.assertIn("未保留也未声明删除的当前用例：验证登录成功（case-a）", calls[1])
        self.assertIn("removedCases", calls[0])
        # Both cases survive and keep the identity the platform issued before.
        self.assertEqual(
            sorted((item["case_id"], item["case_title"]) for item in cases),
            sorted((item["case_id"], item["case_title"]) for item in previous),
        )

    def test_revision_that_keeps_dropping_a_case_fails_instead_of_losing_it(self):
        with self.assertRaises(OutputValidationError) as caught:
            self.run_revision([{"cases": [case("验证登录失败", "login")]}])

        message = str(caught.exception)
        self.assertIn("detailed_cases/login 修订未通过校验", message)
        self.assertIn("验证登录成功（case-a）", message)

    def test_revision_may_remove_a_case_it_declares_with_a_reason(self):
        cases, calls, _previous = self.run_revision(
            [
                {
                    "cases": [case("验证登录失败", "login")],
                    "removedCases": [{"caseId": "case-a", "reason": "对应需求已取消"}],
                }
            ]
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual([item["case_id"] for item in cases], ["case-b"])

    def test_revision_summary_reports_how_many_cases_were_removed(self):
        def batches(**kwargs):
            return json.dumps({"cases": [{"case_id": "case-b", **case("验证登录失败", "login")}]})

        task = self.task("detailed_cases")
        config = json.loads(task.config_json)
        config["resultYaml"] = json.dumps(
            {
                "cases": [
                    {"case_id": "case-a", **case("验证登录成功")},
                    {"case_id": "case-b", **case("验证登录失败")},
                ]
            },
            ensure_ascii=False,
        )
        task.config_json = json.dumps(config, ensure_ascii=False)
        result = FunctionalCaseExecutor(
            agent_config=PiConfig(),
            detailed_batch_runner=batches,
            chain_runner=lambda **kwargs: self.fail("must not run full chain"),
            skill_runner=lambda **kwargs: self.fail("must not rerun upstream"),
        ).execute(task, datetime.now().astimezone(), lambda _: None)

        summary = json.loads(result.result_summary_json)
        self.assertEqual(summary["caseCount"], 1)
        self.assertEqual(summary["removedCaseCount"], 1)
