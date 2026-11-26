import json
import tempfile
import unittest
from datetime import datetime

from testing_agent_ai_worker.agent.base import AgentResult
from testing_agent_ai_worker.config.models import PiConfig
from testing_agent_ai_worker.historical_test_case_artifacts import (
    VERIFICATION_BATCH_INPUT,
    VERIFICATION_RUN_INPUT,
    verification_run_header,
)
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.tasks.requirement_analysis.executor import RequirementAnalysisExecutor

IDENTITY = {
    "requirementId": "current",
    "materialSnapshotId": "material",
    "impactResultId": "adopted-relations",
}


def case_body(case_id):
    return {
        "caseId": case_id,
        "caseSnapshotId": f"snapshot-{case_id}",
        "requirementId": "history",
        "suiteId": "history-suite",
        "module": "订单",
        "title": "订单地址规则",
        "contentScope": "full_case",
        "preconditions": [],
        "steps": [
            {"position": 1, "action": "打开地址", "expected": "显示原地址"},
            {"position": 2, "action": "修改地址", "expected": "不允许修改"},
        ],
    }


def batch(batch_id, case=None):
    return {
        **verification_run_header(VERIFICATION_BATCH_INPUT, IDENTITY),
        "batchId": batch_id,
        "impact": {
            "impactId": f"impact-{batch_id}",
            "ruleEffect": "changed",
            "scope": {"roles": [], "states": ["已发货"], "conditions": []},
            "previousRule": "已发货禁止修改地址",
            "currentRule": "已发货未签收允许修改",
            "changeSummary": "扩大地址可修改范围",
        },
        "candidateCases": [{**case, "contentScope": "matched_excerpt", "steps": case["steps"][1:]}]
        if case
        else [],
    }


def frozen_input(batches, cases):
    return {
        **verification_run_header(VERIFICATION_RUN_INPUT, IDENTITY),
        "batches": batches,
        "fullCases": {case["caseId"]: case for case in cases},
    }


def response(source, *, request_full=False):
    return {
        **verification_run_header("historical_test_case_verification", source),
        "batchId": source["batchId"],
        "impactId": source["impact"]["impactId"],
        "caseFindings": [
            {
                "caseId": case["caseId"],
                "caseSnapshotId": case["caseSnapshotId"],
                "decision": "needs_confirmation" if request_full else "modify",
                "evidence": [{"kind": "step", "position": 2}],
                "reason": "原预期与新规则不同",
                "modificationHint": None if request_full else "修改为允许保存",
                "needsFullCase": request_full,
            }
            for case in source["candidateCases"]
        ],
        "supplementalScenarios": [],
    }


class HistoricalVerificationStageTests(unittest.TestCase):
    def execute(self, source, runner, progress):
        task = Task(
            task_id="worker",
            attempt_id="verify-attempt",
            task_type="requirement_analysis",
            current_stage="historical_test_case_verification",
            checkpoint_enabled=True,
            requirement_id=IDENTITY["requirementId"],
            payload=TaskPayload(source_content=json.dumps(source)),
        )
        with tempfile.TemporaryDirectory() as root:
            executor = RequirementAnalysisExecutor(
                agent_config=PiConfig(runtime_root=root), skill_runner=runner
            )
            return executor.execute(task, datetime.now().astimezone(), progress.append)

    def test_batches_use_independent_sessions_and_expand_only_requested_cases(self):
        old_a, old_b = case_body("a"), case_body("b")
        initial = batch("batch-1", old_a)
        initial["candidateCases"].extend(batch("other", old_b)["candidateCases"])
        source = frozen_input([initial, batch("batch-2")], [old_a, old_b])
        calls, progression = [], []

        async def runner(**kwargs):
            payload = json.loads(kwargs["input_text"])
            calls.append((kwargs, payload))
            artifact = response(payload)
            if kwargs["session_key"].endswith("batch-1:firstPass"):
                artifact["caseFindings"][0].update(
                    decision="needs_confirmation", modificationHint=None, needsFullCase=True
                )
            elif payload["batchId"] == "batch-2":
                del artifact["supplementalScenarios"]
                artifact["schemaVersion"] = "0.2"
                artifact["supplementalPoints"] = [
                    {"pointId": "point-1", "title": "验证已发货未签收的订单可以修改地址"}
                ]
            return artifact

        result = self.execute(source, runner, progression)
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(len({call["session_key"] for call, _ in calls}), 3)
        self.assertTrue(
            all(call["skill_name"] == "mtx-verify-historical-test-cases" for call, _ in calls)
        )
        excerpt = calls[0][1]["candidateCases"]
        self.assertEqual([case["contentScope"] for case in excerpt], ["matched_excerpt"] * 2)
        self.assertEqual([len(case["steps"]) for case in excerpt], [1, 1])
        self.assertEqual(calls[1][1]["candidateCases"], [old_a])
        self.assertEqual(calls[2][1]["candidateCases"], [])
        self.assertEqual(len(progression), 3)
        artifact = json.loads(result.output_yaml)
        self.assertEqual(artifact["batches"][0]["fullCasePass"]["caseFindings"][0]["caseId"], "a")
        self.assertIsNone(artifact["batches"][1]["fullCasePass"])
        self.assertEqual(
            artifact["batches"][1]["firstPass"]["supplementalPoints"],
            [{"pointId": "point-1", "title": "验证已发货未签收的订单可以修改地址"}],
        )

    def test_empty_adopted_relation_result_succeeds_without_model_call(self):
        result = self.execute(frozen_input([], []), lambda **_: self.fail("unexpected call"), [])
        self.assertEqual(json.loads(result.output_yaml)["batches"], [])

    def test_final_answer_wrapped_in_prose_or_fence_is_accepted(self):
        old = case_body("old")
        artifact = response(batch("batch-1", old))
        body = json.dumps(artifact)
        replies = {
            "bare": body,
            "fence": f"```json\n{body}\n```",
            "prose": f"校验通过。正式响应如下：\n\n```json\n{body}\n```",
        }
        for shape, content in replies.items():
            with self.subTest(shape):
                result = self.execute(
                    frozen_input([batch("batch-1", old)], [old]),
                    lambda **_: AgentResult(content=content, finish_reason="stop"),
                    [],
                )
                self.assertEqual(result.status, TaskStatus.SUCCESS)
                self.assertEqual(
                    json.loads(result.output_yaml)["batches"][0]["firstPass"], artifact
                )

    def test_excerpt_cannot_return_invalidation(self):
        old = case_body("old")

        def runner(**kwargs):
            artifact = response(json.loads(kwargs["input_text"]))
            artifact["caseFindings"][0].update(decision="invalidate", modificationHint=None)
            return artifact

        with self.assertRaisesRegex(ValueError, "批次结果未通过"):
            self.execute(frozen_input([batch("batch-1", old)], [old]), runner, [])
