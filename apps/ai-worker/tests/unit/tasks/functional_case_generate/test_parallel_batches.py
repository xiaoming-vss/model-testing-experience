"""Program-dispatched module agents are bounded, isolated and observable."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.tasks.functional_case_generate.detailed_batches import (
    run_functional_detailed_case_batches,
)
from testing_agent_ai_worker.tasks.functional_case_generate.validation import (
    ValidationContext,
    context,
)
from tests.unit.tasks.functional_case_generate.fixtures import case, traceable_modules


class ParallelBatchesTests(unittest.IsolatedAsyncioTestCase):
    async def test_modules_overlap_with_distinct_agents_sessions_and_workspaces(self):
        active = peak = 0
        sessions, workspaces, progress = [], [], []
        both_started = asyncio.Event()

        class Bot:
            def __init__(self, workspace):
                self.workspace = workspace

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            async def run_with_subagents(self, *_args, **_kwargs):
                raise AssertionError("module agents must not delegate recursively")

            async def run(self, prompt, *, session_key, **_kwargs):
                nonlocal active, peak
                sessions.append(session_key)
                workspaces.append(self.workspace)
                module = next(name for name in ("A", "B", "C") if f'"module": "{name}"' in prompt)
                active += 1
                peak = max(peak, active)
                if active == 2:
                    both_started.set()
                await asyncio.wait_for(both_started.wait(), 1)
                await asyncio.sleep(0.02 if module == "A" else 0)
                active -= 1
                return json.dumps({"cases": [case(module, module=module)]})

        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "skills"
            skills.mkdir()
            (skills / "marker").write_text("skill")
            token = context.set(ValidationContext(Path(tmp) / "diagnostics", progress.append))
            try:
                result = await run_functional_detailed_case_batches(
                    requirement_analysis_json="{}",
                    case_names_json=json.dumps(traceable_modules("A", "B", "C")),
                    session_key="run",
                    skill_name="skill",
                    workspace=tmp,
                    from_config=lambda **kw: Bot(kw["workspace"]),
                )
            finally:
                context.reset(token)
            self.assertTrue(all((Path(path) / "skills/marker").exists() for path in workspaces))
        self.assertEqual(peak, 2)
        self.assertEqual(len(set(sessions)), 3)
        self.assertEqual(len(set(workspaces)), 3)
        self.assertEqual([c["case_module"] for c in json.loads(result)["cases"]], ["A", "B", "C"])
        snapshots = [p["moduleGeneration"] for p in progress if "moduleGeneration" in p]
        self.assertTrue(
            any(sum(m["status"] == "running" for m in p["modules"]) == 2 for p in snapshots)
        )
        self.assertEqual(snapshots[-1]["status"], "completed")
        self.assertEqual([p["sequence"] for p in snapshots], list(range(1, len(snapshots) + 1)))
        self.assertTrue(all(m["status"] == "queued" for m in snapshots[0]["modules"]))

    async def test_failure_cancels_running_and_queued_modules_without_partial_result(self):
        started = asyncio.Event()
        closed, progress = [], []

        class Bot:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                closed.append(True)

            async def run(self, prompt, **_kwargs):
                if '"module": "A"' in prompt:
                    await started.wait()
                    raise RuntimeError("model unavailable")
                started.set()
                await asyncio.Event().wait()

        with tempfile.TemporaryDirectory() as tmp:
            token = context.set(ValidationContext(Path(tmp), progress.append))
            try:
                with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                    await asyncio.wait_for(
                        run_functional_detailed_case_batches(
                            requirement_analysis_json="{}",
                            case_names_json=json.dumps(traceable_modules("A", "B", "C")),
                            session_key="run",
                            skill_name="skill",
                            from_config=lambda **_: Bot(),
                        ),
                        2,
                    )
            finally:
                context.reset(token)
        self.assertEqual(len(closed), 2)
        last = [p["moduleGeneration"] for p in progress if "moduleGeneration" in p][-1]
        self.assertEqual(last["status"], "failed")
        self.assertEqual([m["status"] for m in last["modules"]], ["failed", "canceled", "canceled"])

    async def test_external_cancellation_waits_for_all_agent_cleanup(self):
        active = 0
        started = asyncio.Event()
        closed, progress = [], []

        class Bot:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                closed.append(True)

            async def run(self, _prompt, **_kwargs):
                nonlocal active
                active += 1
                if active == 2:
                    started.set()
                await asyncio.Event().wait()

        with tempfile.TemporaryDirectory() as tmp:
            token = context.set(ValidationContext(Path(tmp), progress.append))
            try:
                task = asyncio.create_task(
                    run_functional_detailed_case_batches(
                        requirement_analysis_json="{}",
                        case_names_json=json.dumps(traceable_modules("A", "B", "C")),
                        session_key="run",
                        skill_name="skill",
                        from_config=lambda **_: Bot(),
                    )
                )
                await asyncio.wait_for(started.wait(), 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                context.reset(token)
        self.assertEqual(len(closed), 2)
        last = [p["moduleGeneration"] for p in progress if "moduleGeneration" in p][-1]
        self.assertEqual(last["status"], "canceled")
        self.assertTrue(all(m["status"] == "canceled" for m in last["modules"]))
