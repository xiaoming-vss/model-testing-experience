"""Partitioned point drafts still require complete independent review."""

import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.tasks.functional_case_generate.traceable_review import (
    generate_traceable_points,
)
from testing_agent_ai_worker.tasks.functional_case_generate.validation import (
    ValidationContext,
    context,
)
from tests.unit.tasks.functional_case_generate.fixtures import analysis, traceable_points


def scope_with_objects(count=2):
    value = analysis()
    value["testObjects"] = [
        {
            "id": f"O{i}",
            "name": f"对象{i}",
            "type": "功能",
            "description": f"规则{i}",
            "basisStatus": "confirmed",
            "sourceBlockIds": ["B1"],
        }
        for i in range(1, count + 1)
    ]
    return value


def point_output(ids, name="【登录】验证登录"):
    value = traceable_points()
    value["testPoints"][0].update(testObjectIds=ids, name=name)
    return value


class ParallelPointTests(unittest.IsolatedAsyncioTestCase):
    async def run_points(self, generate, *, scope=None, parallel=True):
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "skills/points/references"
            ref.mkdir(parents=True)
            for filename in ["design-audit.md", "independent-review.md"]:
                (ref / filename).write_text("review rules")
            token = context.set(ValidationContext(Path(tmp) / "diagnostics", events.append))
            try:
                result = await generate_traceable_points(
                    generation_input="frozen material and scope",
                    material={"materialBlocks": [{"id": "B1"}], "questions": []},
                    scope=scope or scope_with_objects(),
                    workspace=tmp,
                    generate=generate,
                    skill_name="points",
                    parallel_draft=parallel,
                )
            finally:
                context.reset(token)
        return json.loads(result), events

    async def test_parallel_groups_merge_unique_ids_then_run_global_review(self):
        active = peak = 0
        ready = asyncio.Event()
        calls = []

        async def generate(prompt, phase):
            nonlocal active, peak
            calls.append((prompt, phase))
            if phase.startswith("draft-"):
                active += 1
                peak = max(peak, active)
                if active == 2:
                    ready.set()
                await asyncio.wait_for(ready.wait(), 1)
                index = int(phase.rsplit("-", 1)[1])
                await asyncio.sleep(0.01)
                active -= 1
                ids = [["O1"], ["O2"], ["O1", "O2"]][index]
                return json.dumps(point_output(ids, f"【登录】验证规则{index}"))
            self.assertEqual(active, 0)
            return '{"issues":[]}'

        result, events = await self.run_points(generate)
        self.assertEqual(peak, 2)
        self.assertEqual(len([p for _, p in calls if p.startswith("draft-")]), 3)
        self.assertEqual(len(result["testPoints"]), 3)
        self.assertEqual(len({p["id"] for p in result["testPoints"]}), 3)
        self.assertEqual(result["reviewStatus"], "independent_reviewed")
        coverage = next(prompt for prompt, phase in calls if "-coverage-" in phase)
        for point in result["testPoints"]:
            self.assertIn(point["name"], coverage)
        states = [event["moduleGeneration"] for event in events if "moduleGeneration" in event]
        self.assertEqual(states[-1]["status"], "completed")
        self.assertEqual(states[-1]["stage"], "case_names")
        self.assertTrue(any(s["status"] == "reviewing" for s in states))
        self.assertTrue(all(m["pointCount"] == 1 for m in states[-1]["modules"]))

    async def test_group_boundary_violation_is_repaired_before_review(self):
        group_calls = {}

        async def generate(prompt, phase):
            if not phase.startswith("draft-"):
                return '{"issues":[]}'
            index = int(phase.rsplit("-", 1)[1])
            group_calls[index] = group_calls.get(index, 0) + 1
            ids = [["O1"], ["O2"], []][index]
            if index == 0 and group_calls[index] == 1:
                ids = ["O2"]
            if index == 0 and group_calls[index] == 2:
                self.assertIn("分组范围", prompt)
            return json.dumps(point_output(ids, f"【登录】验证规则{index}"))

        result, _ = await self.run_points(generate)
        self.assertEqual(group_calls, {0: 2, 1: 1, 2: 1})
        self.assertEqual(result["reviewStatus"], "independent_reviewed")

    async def test_failed_group_cancels_siblings_and_never_audits_partial_draft(self):
        started = asyncio.Event()
        canceled = []

        async def generate(_prompt, phase):
            self.assertTrue(phase.startswith("draft-"))
            if phase.endswith("-0"):
                await started.wait()
                raise RuntimeError("group failed")
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                canceled.append(phase)

        with self.assertRaisesRegex(RuntimeError, "group failed"):
            await asyncio.wait_for(self.run_points(generate), 2)
        self.assertEqual(len(canceled), 1)

    async def test_correction_does_not_regenerate_groups_and_keeps_ids(self):
        phase_calls = []
        current = None

        async def generate(prompt, phase):
            nonlocal current
            phase_calls.append(phase)
            if phase.startswith("draft-"):
                index = int(phase.rsplit("-", 1)[1])
                return json.dumps(
                    point_output([["O1"], ["O2"], []][index], f"【登录】验证规则{index}")
                )
            if phase.startswith("audit-0-basis-"):
                entries = json.loads(prompt.split("【待审内容】\n")[1].split("\n\n")[0])
                current = entries
                issue = {k: copy.deepcopy(v) for k, v in entries[0].items() if k.endswith("Ids")}
                issue.update(
                    kind="unsupported",
                    targetType="testPoint",
                    targetId=entries[0]["id"],
                    issue="条件不完整",
                    suggestion="修正条件",
                )
                return json.dumps({"issues": [issue]})
            if phase.startswith("correct-"):
                value = json.loads(prompt.split("【当前候选】\n")[1].split("\n\n")[0])
                value["testPoints"][0]["name"] += "边界"
                return json.dumps(value)
            return '{"issues":[]}'

        result, events = await self.run_points(generate)
        self.assertEqual(len([p for p in phase_calls if p.startswith("draft-")]), 3)
        self.assertEqual([p["id"] for p in result["testPoints"]], [p["id"] for p in current])
        self.assertTrue(
            any(e.get("moduleGeneration", {}).get("status") == "revising" for e in events)
        )

    async def test_small_or_explicit_revision_uses_existing_single_generation(self):
        for scope, parallel in [(scope_with_objects(1), True), (scope_with_objects(), False)]:
            phases = []

            async def generate(_prompt, phase):
                phases.append(phase)
                return json.dumps(point_output(["O1"])) if phase == "generate" else '{"issues":[]}'

            result, _ = await self.run_points(generate, scope=scope, parallel=parallel)
            self.assertEqual(result["reviewStatus"], "independent_reviewed")
            self.assertEqual(phases[0], "generate")
            self.assertFalse(any(p.startswith("draft-") for p in phases))

    def test_many_objects_are_bounded_and_exact_duplicates_only_are_merged(self):
        from testing_agent_ai_worker.tasks.functional_case_generate.point_drafts import (
            draft_groups,
            merge_drafts,
        )

        scope = scope_with_objects(22)
        groups = draft_groups(scope)
        self.assertEqual(len(groups), 4)
        assigned = [object_id for group in groups for object_id in group.object_ids]
        self.assertEqual(assigned, [row["id"] for row in scope["testObjects"]])
        value = point_output(["O1"])
        value["testPoints"].append({**value["testPoints"][0], "id": "another-id"})
        other = point_output(["O2"])
        result = json.loads(
            merge_drafts(
                [json.dumps(value), json.dumps(other)],
                {"materialBlocks": [{"id": "B1"}], "questions": []},
                scope,
            )
        )
        self.assertEqual(len(result["testPoints"]), 2)
        self.assertEqual([p["testObjectIds"] for p in result["testPoints"]], [["O1"], ["O2"]])

    async def test_unresolved_review_is_not_reported_as_generation_complete(self):
        candidate = None

        async def generate(prompt, phase):
            nonlocal candidate
            if phase.startswith("draft-"):
                index = int(phase.rsplit("-", 1)[1])
                return json.dumps(
                    point_output([["O1"], ["O2"], []][index], f"【登录】验证规则{index}")
                )
            if "-basis-" in phase:
                entries = json.loads(prompt.split("【待审内容】\n")[1].split("\n\n")[0])
                issue = {k: v for k, v in entries[0].items() if k.endswith("Ids")}
                issue.update(
                    kind="unsupported",
                    targetType="testPoint",
                    targetId=entries[0]["id"],
                    issue="缺少业务依据",
                    suggestion="确认依据",
                )
                return json.dumps({"issues": [issue]})
            if phase.startswith("correct-"):
                candidate = json.loads(prompt.split("【当前候选】\n")[1].split("\n\n")[0])
                return json.dumps(candidate)
            return '{"issues":[]}'

        result, events = await self.run_points(generate)
        self.assertEqual(result["reviewStatus"], "independent_review_failed")
        latest = [e["moduleGeneration"] for e in events if "moduleGeneration" in e][-1]
        self.assertEqual(latest["status"], "review_failed")
        self.assertEqual(latest["issueCount"], 1)

    async def test_cancelling_parallel_drafts_stops_all_started_groups(self):
        started = asyncio.Event()
        count = 0
        stopped = []

        async def generate(_prompt, phase):
            nonlocal count
            count += 1
            if count == 2:
                started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(phase)

        task = asyncio.create_task(self.run_points(generate))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(len(stopped), 2)
