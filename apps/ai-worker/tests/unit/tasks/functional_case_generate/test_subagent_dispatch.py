"""Delegation is scoped to functional generation and independent reviews."""

import json
import unittest
from types import SimpleNamespace

from testing_agent_ai_worker.agent.base import AgentResult
from testing_agent_ai_worker.tasks.functional_case_generate.chain import (
    _run_traceable_phase,
    run_functional_chain,
)
from testing_agent_ai_worker.tasks.functional_case_generate.detailed_batches import (
    run_functional_detailed_case_batches,
)
from testing_agent_ai_worker.tasks.functional_case_generate.traceable_review import (
    generate_traceable_points,
)
from testing_agent_ai_worker.tasks.functional_case_generate.validation import OutputValidationError
from tests.unit.tasks.functional_case_generate.fixtures import analysis, case, traceable_modules


class RecordingAgent:
    def __init__(self):
        self.calls = []

    async def run(self, prompt, **kwargs):
        self.calls.append(("normal", prompt, kwargs))
        return "normal"

    async def run_with_subagents(self, prompt, **kwargs):
        self.calls.append(("delegated", prompt, kwargs))
        return "delegated"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class SubagentDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_autonomous_review_receives_all_points_and_all_three_checks(self):
        import tempfile
        from pathlib import Path

        points = traceable_modules(*(f"模块{i}" for i in range(21)))
        seen = {}

        async def generate(prompt, phase):
            if phase == "generate":
                return json.dumps(points)
            seen[phase] = prompt
            return AgentResult(
                content='{"issues":[]}', finish_reason="stop", usage={"subagent_count": 1}
            )

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "skills/mtx-generate-traceable-test-points/references"
            ref.mkdir(parents=True)
            for name in ("design-audit.md", "independent-review.md", "subagent.md"):
                (ref / name).write_text("test review rules")
            result = await generate_traceable_points(
                generation_input="input",
                material={"materialBlocks": [{"id": "B1"}], "questions": []},
                scope={"testObjects": [], "impactAreas": [], "risks": [], "openQuestions": []},
                workspace=tmp,
                generate=generate,
                autonomous_review=True,
                skill_name="mtx-generate-traceable-test-points",
            )
        self.assertEqual(json.loads(result)["reviewStatus"], "independent_reviewed")
        self.assertEqual(
            set(seen),
            {
                "audit-0-basis-0",
                "audit-0-basis-1",
                "audit-0-basis-2",
                "audit-0-coverage-3",
                "audit-0-gaps-4",
            },
        )
        self.assertNotIn('"id": "P21"', seen["audit-0-basis-0"])
        self.assertIn('"id": "P21"', seen["audit-0-basis-2"])
        self.assertIn("test review rules", seen["audit-0-basis-0"])

    async def test_large_basis_review_splits_at_ten_with_delegation(self):
        import tempfile
        from pathlib import Path

        points = traceable_modules(*(f"模块{i}" for i in range(21)))
        seen = {}

        async def generate(prompt, phase):
            if phase == "generate":
                return json.dumps(points)
            seen[phase] = prompt
            return AgentResult(content='{"issues":[]}', finish_reason="stop")

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "skills/mtx-generate-traceable-test-points/references"
            ref.mkdir(parents=True)
            for name in ("design-audit.md", "independent-review.md", "subagent.md"):
                (ref / name).write_text("rules")
            result = await generate_traceable_points(
                generation_input="input",
                material={"materialBlocks": [{"id": "B1"}], "questions": []},
                scope={"testObjects": [], "impactAreas": [], "risks": [], "openQuestions": []},
                workspace=tmp,
                generate=generate,
                skill_name="mtx-generate-traceable-test-points",
                autonomous_review=True,
            )
        self.assertEqual(json.loads(result)["reviewStatus"], "independent_reviewed")
        self.assertEqual(
            {name for name in seen if "basis" in name},
            {"audit-0-basis-0", "audit-0-basis-1", "audit-0-basis-2"},
        )
        self.assertIn('"id": "P21"', seen["audit-0-basis-2"])
        self.assertNotIn('"id": "P21"', seen["audit-0-basis-0"])

    async def test_detailed_generation_dispatches_modules_in_both_paths_and_keeps_identity(self):
        calls = []

        class Bot(RecordingAgent):
            async def run(self, prompt, **kwargs):
                calls.append((prompt, kwargs))
                return SimpleNamespace(content=json.dumps({"cases": [case(module="登录")]}))

        def factory(**_):
            return Bot()

        names = json.dumps(traceable_modules("登录"), ensure_ascii=False)
        old = {**case(module="登录"), "case_id": "existing-id"}
        result = await run_functional_detailed_case_batches(
            source_text="冻结材料",
            requirement_analysis_json=json.dumps(analysis(), ensure_ascii=False),
            case_names_json=names,
            session_key="session",
            skill_name="mtx-generate-solution-test-cases",
            current_cases_json=json.dumps({"cases": [old]}, ensure_ascii=False),
            revision_instruction="优化预期",
            media=["/image.png"],
            from_config=factory,
        )
        self.assertEqual(json.loads(result)["cases"][0]["case_id"], "existing-id")
        self.assertIn("优化预期", calls[0][0])
        self.assertIn("独立模块任务", calls[0][0])
        self.assertEqual(calls[0][1]["media"], ["/image.png"])
        self.assertNotIn("delegation_kind", calls[0][1])

        result = await run_functional_chain(
            source_text="冻结材料",
            session_key="session",
            analysis_skill_name="mtx-analyze-functional-requirements",
            case_name_skill_name="mtx-generate-traceable-test-points",
            detailed_case_skill_name="mtx-generate-solution-test-cases",
            resume_stage="detailed_cases",
            prior_analysis=json.dumps(analysis(), ensure_ascii=False),
            prior_case_names=names,
            from_config=factory,
        )
        self.assertEqual(len(json.loads(result.detailed_cases_output)["cases"]), 1)
        self.assertNotIn("delegation_kind", calls[-1][1])

    async def test_clarification_from_module_prevents_case_publication(self):
        class Bot(RecordingAgent):
            async def run(self, prompt, **kwargs):
                return SimpleNamespace(content="CLARIFICATION_REQUIRED: 缺少审批结果")

        with self.assertRaisesRegex(OutputValidationError, "缺少审批结果"):
            await run_functional_detailed_case_batches(
                requirement_analysis_json=json.dumps(analysis()),
                case_names_json=json.dumps(traceable_modules("登录")),
                session_key="session",
                skill_name="mtx-generate-solution-test-cases",
                from_config=lambda **_: Bot(),
            )

    async def test_draft_and_independent_review_support_delegation(self):
        parent = RecordingAgent()
        reviewer = RecordingAgent()

        def factory(**_):
            return reviewer

        async def run(phase):
            return await _run_traceable_phase(
                factory=factory,
                bot=parent,
                config_path="config",
                workspace="workspace",
                session_key="session",
                prompt="frozen input",
                phase=phase,
                media_args={},
            )

        self.assertEqual(await run("generate"), "delegated")
        self.assertEqual(await run("correct-0"), "normal")
        self.assertEqual(await run("audit-0-basis-0"), "delegated")
        self.assertEqual(parent.calls[1][2]["session_key"], "session:correct-0")
        self.assertEqual(reviewer.calls[0][2]["session_key"], "session:audit-0-basis-0")
        self.assertEqual(reviewer.calls[0][2]["delegation_kind"], "test_point_review")

    async def test_backend_without_delegation_keeps_existing_behavior(self):
        class ExistingAgent:
            async def run(self, prompt, **kwargs):
                return (prompt, kwargs)

        result = await _run_traceable_phase(
            factory=None,
            bot=ExistingAgent(),
            config_path="config",
            workspace="workspace",
            session_key="session",
            prompt="frozen input",
            phase="generate",
            media_args={},
        )
        self.assertEqual(result, ("frozen input", {"session_key": "session"}))

    async def test_program_point_groups_use_separate_workspaces_sessions_and_no_nested_delegation(
        self,
    ):
        import asyncio
        import tempfile
        from pathlib import Path

        calls = []

        class GroupAgent(RecordingAgent):
            def __init__(self, workspace):
                super().__init__()
                self.workspace = workspace

            async def run(self, prompt, **kwargs):
                calls.append((self, self.workspace, kwargs))
                return "ok"

            async def run_with_subagents(self, *_args, **_kwargs):
                raise AssertionError("group must not delegate recursively")

        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "skills"
            skills.mkdir()
            (skills / "marker").write_text("frozen skill")

            async def run(index):
                return await _run_traceable_phase(
                    factory=lambda **kw: GroupAgent(kw["workspace"]),
                    bot=RecordingAgent(),
                    config_path="config",
                    workspace=tmp,
                    session_key="session",
                    prompt="frozen material",
                    phase=f"draft-dispatch-{index}",
                    media_args={"media": ["/image.png"]},
                )

            await asyncio.gather(run(0), run(1))
            await run(0)  # Format repair resumes only its own isolated session.
            group_zero = [call for call in calls if call[2]["session_key"].endswith("-0")]
            group_one = next(call for call in calls if call[2]["session_key"].endswith("-1"))
            self.assertNotEqual(group_zero[0][0], group_one[0])
            self.assertNotEqual(group_zero[0][1], group_one[1])
            self.assertEqual(group_zero[0][1], group_zero[1][1])
            self.assertEqual(group_zero[0][2]["session_key"], group_zero[1][2]["session_key"])
            self.assertEqual(group_one[2]["media"], ["/image.png"])
            self.assertTrue(
                all(
                    (Path(workspace) / "skills/marker").read_text() == "frozen skill"
                    for _, workspace, _ in calls
                )
            )
