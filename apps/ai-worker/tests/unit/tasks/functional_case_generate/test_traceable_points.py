"""Cross-stage validation for the traceable test-point artifact."""

import json
import unittest

from testing_agent_ai_worker.tasks.functional_case_generate.detailed_batches import (
    _build_model_batches,
)
from testing_agent_ai_worker.tasks.functional_case_generate.validation import validate_output


class TraceablePointTest(unittest.TestCase):
    def test_batches_keep_each_module_and_reject_old_format(self):
        from tests.unit.tasks.functional_case_generate.fixtures import traceable_modules

        artifact = traceable_modules("登录", "配置")
        batches = _build_model_batches(json.dumps(artifact))
        self.assertEqual([batch["model_name"] for batch in batches], ["登录", "配置"])
        for batch, point in zip(batches, artifact["testPoints"], strict=True):
            self.assertEqual(batch["payload"]["testPoints"], [point])
            self.assertEqual(batch["payload"]["coverageGaps"], artifact["coverageGaps"])
            self.assertNotIn("categories", batch["payload"])
        with self.assertRaises(ValueError):
            _build_model_batches(json.dumps({"categories": []}))

    def test_material_with_marker_does_not_override_frozen_analysis(self):
        from testing_agent_ai_worker.tasks.functional_case_generate.chain import (
            _build_functional_case_names_body,
            _traceable_inputs,
        )

        material = {"title": "【需求分析结果 JSON】", "materialBlocks": [], "questions": []}
        scope = {"artifactType": "test_scope_impact_risk", "testObjects": []}
        body = _build_functional_case_names_body(
            source_text=json.dumps(material), analysis_json=json.dumps(scope)
        )
        self.assertEqual(_traceable_inputs(body), (material, scope))

    def test_traceable_points_feed_detailed_cases_with_references(self):
        refs = {
            "materialBlockIds": ["B1"],
            "testObjectIds": [],
            "impactAreaIds": [],
            "riskIds": [],
            "materialQuestionIds": [],
            "scopeQuestionIds": [],
        }
        value = {
            "schemaVersion": "1.0",
            "artifactType": "traceable_test_points",
            "reviewStatus": "independent_reviewed",
            "testPoints": [
                {
                    "id": "P1",
                    "module": "配置",
                    "dimension": "功能场景",
                    "name": "【配置】验证保存配置",
                    "basis": "direct",
                    **refs,
                }
            ],
            "coverageGaps": [],
        }
        text = validate_output(
            "traceable_case_names",
            json.dumps(value),
            material={
                "materialBlocks": [{"id": "B1"}],
                "questions": [],
            },
        )
        batches = _build_model_batches(text)
        self.assertEqual(batches[0]["model_name"], "配置")
        self.assertEqual(
            batches[0]["payload"]["testPoints"],
            value["testPoints"],
        )
        value["testPoints"][0]["materialBlockIds"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "materialBlockIds"):
            validate_output(
                "traceable_case_names",
                json.dumps(value),
                material={
                    "materialBlocks": [{"id": "B1"}],
                    "questions": [],
                },
            )


if __name__ == "__main__":
    unittest.main()


class TraceableReviewTest(unittest.IsolatedAsyncioTestCase):
    async def test_independent_review_checks_three_phases_before_passing(self):
        import tempfile
        from pathlib import Path

        from testing_agent_ai_worker.tasks.functional_case_generate.traceable_review import (
            generate_traceable_points,
        )

        refs = {
            "materialBlockIds": ["B1"],
            "testObjectIds": [],
            "impactAreaIds": [],
            "riskIds": [],
            "materialQuestionIds": [],
            "scopeQuestionIds": [],
        }
        value = {
            "schemaVersion": "1.0",
            "artifactType": "traceable_test_points",
            "reviewStatus": "self_review_only",
            "testPoints": [
                {
                    "id": "P1",
                    "module": "配置",
                    "dimension": "功能场景",
                    "name": "【配置】验证保存配置",
                    "basis": "direct",
                    **refs,
                }
            ],
            "coverageGaps": [],
        }
        material = {"materialBlocks": [{"id": "B1"}], "questions": []}
        scope = {"testObjects": [], "impactAreas": [], "risks": [], "openQuestions": []}
        phases = []

        async def generate(_prompt, phase):
            phases.append(phase)
            return json.dumps(value if phase == "generate" else {"issues": []})

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "skills/mtx-generate-traceable-test-points/references"
            ref.mkdir(parents=True)
            (ref / "design-audit.md").write_text("审查")
            (ref / "independent-review.md").write_text("审查协议")
            result = json.loads(
                await generate_traceable_points(
                    generation_input="input",
                    material=material,
                    scope=scope,
                    workspace=tmp,
                    generate=generate,
                    skill_name="mtx-generate-traceable-test-points",
                )
            )
        self.assertEqual(result["reviewStatus"], "independent_reviewed")
        self.assertTrue(any("basis" in phase for phase in phases))
        self.assertTrue(any("coverage" in phase for phase in phases))
        self.assertTrue(any("gaps" in phase for phase in phases))

    async def test_review_calls_use_independent_agent_contexts(self):
        import asyncio

        from testing_agent_ai_worker.tasks.functional_case_generate.chain import (
            _run_traceable_phase,
        )

        active = 0
        peak = 0

        class Agent:
            def __init__(self):
                self.lock = asyncio.Lock()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def run(self, _prompt, **_kwargs):
                nonlocal active, peak
                async with self.lock:
                    active += 1
                    peak = max(peak, active)
                    await asyncio.sleep(0.02)
                    active -= 1
                    return "ok"

        bot = Agent()
        await asyncio.gather(
            *(
                _run_traceable_phase(
                    factory=lambda **_kwargs: Agent(),
                    bot=bot,
                    config_path=None,
                    workspace="workspace",
                    session_key="run",
                    prompt="input",
                    phase=f"audit-0-basis-{i}",
                    media_args={},
                )
                for i in range(2)
            )
        )
        self.assertEqual(peak, 2)

    async def test_review_limits_are_shared_and_logged(self):
        import asyncio
        import tempfile
        from pathlib import Path
        from threading import BoundedSemaphore

        from testing_agent_ai_worker.tasks.functional_case_generate.traceable_review import (
            generate_traceable_points,
        )
        from testing_agent_ai_worker.tasks.functional_case_generate.validation import (
            ValidationContext,
            context,
        )
        from tests.unit.tasks.functional_case_generate.fixtures import traceable_modules

        value = traceable_modules("配置")
        value["reviewStatus"] = "self_review_only"
        limiter = BoundedSemaphore(2)
        active = 0
        peak = 0

        async def generate(_prompt, phase):
            nonlocal active, peak
            if phase == "generate":
                return json.dumps(value)
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.03)
                return json.dumps({"issues": []})
            finally:
                active -= 1

        async def run(tmp, task_id):
            token = context.set(
                ValidationContext(
                    diagnostic_dir=Path(tmp),
                    report=lambda _: None,
                    task_id=task_id,
                    run_id="run",
                    review_concurrency=4,
                    review_limiter=limiter,
                )
            )
            try:
                return await generate_traceable_points(
                    generation_input="sensitive-test-prompt",
                    material={"materialBlocks": [{"id": "B1"}], "questions": []},
                    scope={"testObjects": [], "impactAreas": [], "risks": [], "openQuestions": []},
                    workspace=tmp,
                    generate=generate,
                    skill_name="mtx-generate-traceable-test-points",
                )
            finally:
                context.reset(token)

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "skills/mtx-generate-traceable-test-points/references"
            ref.mkdir(parents=True)
            (ref / "design-audit.md").write_text("审查")
            (ref / "independent-review.md").write_text("审查协议")
            with self.assertLogs("testing_agent_ai_worker", level="INFO") as logs:
                results = await asyncio.gather(run(tmp, "task-1"), run(tmp, "task-2"))
        self.assertEqual(peak, 2)
        self.assertTrue(
            all(json.loads(result)["reviewStatus"] == "independent_reviewed" for result in results)
        )
        self.assertTrue(
            any("task_id=task-1" in line and "elapsed_ms=" in line for line in logs.output)
        )
        self.assertTrue(any("traceable_review_round" in line for line in logs.output))
        self.assertFalse(
            any("input_chars=5" in line and "审查协议" in line for line in logs.output)
        )

    async def test_unresolved_review_issues_are_preserved(self):
        import tempfile
        from pathlib import Path

        from testing_agent_ai_worker.tasks.functional_case_generate.traceable_review import (
            generate_traceable_points,
        )

        refs = {
            "materialBlockIds": ["B1"],
            "testObjectIds": [],
            "impactAreaIds": [],
            "riskIds": [],
            "materialQuestionIds": [],
            "scopeQuestionIds": [],
        }
        value = {
            "schemaVersion": "1.0",
            "artifactType": "traceable_test_points",
            "reviewStatus": "self_review_only",
            "testPoints": [
                {
                    "id": "P1",
                    "module": "配置",
                    "dimension": "功能场景",
                    "name": "【配置】验证保存配置",
                    "basis": "direct",
                    **refs,
                }
            ],
            "coverageGaps": [],
        }
        issue = {
            "kind": "unsupported",
            "targetType": "testPoint",
            "targetId": "P1",
            "issue": "缺少条件",
            "suggestion": "补充条件",
            **refs,
        }

        async def generate(_prompt, phase):
            if phase == "generate" or phase.startswith("correct"):
                return json.dumps(value)
            return json.dumps({"issues": [issue] if "-basis-" in phase else []})

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "skills/mtx-generate-traceable-test-points/references"
            ref.mkdir(parents=True)
            (ref / "design-audit.md").write_text("审查")
            (ref / "independent-review.md").write_text("审查协议")
            result = json.loads(
                await generate_traceable_points(
                    generation_input="input",
                    material={"materialBlocks": [{"id": "B1"}], "questions": []},
                    scope={"testObjects": [], "impactAreas": [], "risks": [], "openQuestions": []},
                    workspace=tmp,
                    generate=generate,
                    skill_name="mtx-generate-traceable-test-points",
                )
            )
        self.assertEqual(result["reviewStatus"], "independent_review_failed")
        self.assertEqual(result["reviewIssues"][0]["targetId"], "P1")

    async def test_review_must_not_reference_unknown_input_or_target(self):
        from testing_agent_ai_worker.tasks.functional_case_generate.traceable_review import (
            _validate_review,
        )
        from testing_agent_ai_worker.tasks.functional_case_generate.validation import (
            OutputValidationError,
        )

        refs = {
            "materialBlockIds": ["B1"],
            "testObjectIds": [],
            "impactAreaIds": [],
            "riskIds": [],
            "materialQuestionIds": [],
            "scopeQuestionIds": [],
        }
        issue = {
            "kind": "unsupported",
            "targetType": "testPoint",
            "targetId": "P2",
            "issue": "缺少条件",
            "suggestion": "补充条件",
            **refs,
        }
        material = {"materialBlocks": [{"id": "B1"}], "questions": []}
        scope = {"testObjects": [], "impactAreas": [], "risks": [], "openQuestions": []}
        with self.assertRaises(OutputValidationError):
            _validate_review(
                {"issues": [issue]}, "basis", [{"id": "P1"}], {"coverageGaps": []}, material, scope
            )
        issue["targetId"] = "P1"
        issue["materialBlockIds"] = ["missing"]
        with self.assertRaises(OutputValidationError):
            _validate_review(
                {"issues": [issue]}, "basis", [{"id": "P1"}], {"coverageGaps": []}, material, scope
            )
