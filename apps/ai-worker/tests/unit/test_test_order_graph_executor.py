"""测试单图谱执行器：分批逐轮调用、失败重试、轮次归档与临时文件生命周期。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from testing_agent_ai_worker.config.models import NanobotConfig
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.tasks.test_order_graph.executor import (
    TEST_ORDER_GRAPH_SKILL_NAME,
    TestOrderGraphExecutor,
    parse_graph_input,
)
from testing_agent_ai_worker.tasks.test_order_graph.rounds import GRAPH_BATCH_SIZE, empty_graph

GRAPH_WITH_EDGE = {
    "schema_version": "2.0",
    "main_paths": [{"path_id": "P01", "case_ids": ["C01", "C02"]}],
    "edges": [
        {
            "edge_id": "E01",
            "from_case_id": "C01",
            "to_case_id": "C02",
            "relation_type": "next",
            "order": 1,
        }
    ],
}


def make_case(case_id: str, *, steps: bool = True) -> dict:
    return {
        "case_id": case_id,
        "case_module": "系统配置",
        "case_title": f"验证{case_id}",
        "case_type": "配置相关",
        "priority": "2",
        "precondition": ["1. 已登录。"],
        "test_steps": ["1. 打开开关。"] if steps else [],
        "expected_results": ["1. 保存成功。"] if steps else [],
    }


def make_graph_input(case_ids: list[str], requirement_id: str | None = "REQ-001") -> dict:
    return {
        "requirements": [
            {
                "requirement_id": "REQ-001",
                "requirement_title": "本地清洗开关配置",
                "requirement_content": "管理员可以开启或关闭「启用本地清洗」开关。",
            }
        ],
        "cases": [make_case(case_id) for case_id in case_ids],
        "case_requirement_links": [{"requirement_id": requirement_id, "case_ids": case_ids}],
    }


class _RecordingSkillRunner:
    """按顺序返回预设输出，并记录每轮的调用参数。"""

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.outputs) - 1)
        return self.outputs[index]


def _body_payload(call: dict[str, object]) -> dict:
    """取回 prompt 正文里的输入 JSON（正文之后还拼了路径提示与重试说明）。"""

    return json.loads(str(call["input_text"]).split("\n\n")[0])


class ParseGraphInputTest(unittest.TestCase):
    def test_reads_payload_from_config_json(self) -> None:
        payload = make_graph_input(["C01"])
        task = Task(
            task_id="task-1",
            run_id="run-1",
            generate_task_id="generate-1",
            task_type="test_order_graph",
            config_json=json.dumps({"graphInput": payload}, ensure_ascii=False),
            payload=TaskPayload(openapi_content=""),
        )

        self.assertEqual(payload, parse_graph_input(task.config_json))


class TestOrderGraphExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.runtime_root = Path(self._temp.name)
        self.workspace = self.runtime_root / "workspaces" / "project-project-1"

    def _task(self, payload: dict, *, run_id: str = "run-1") -> Task:
        return Task(
            task_id="task-1",
            run_id=run_id,
            generate_task_id="generate-1",
            task_type="test_order_graph",
            project_id="project-1",
            sprint_id="sprint-1",
            config_json=json.dumps({"graphInput": payload}, ensure_ascii=False),
            payload=TaskPayload(openapi_content=""),
        )

    def _executor(self, skill_runner, *, skill_dir_exists: bool = True) -> TestOrderGraphExecutor:
        if skill_dir_exists:
            (self.workspace / "skills" / TEST_ORDER_GRAPH_SKILL_NAME).mkdir(parents=True)
        return TestOrderGraphExecutor(
            nanobot_config=NanobotConfig(runtime_root=str(self.runtime_root)),
            skill_runner=skill_runner,
            skill_dir_checker=lambda workspace, skill_name: (
                workspace / "skills" / skill_name
            ).exists(),
        )

    def _execute(self, task: Task, executor: TestOrderGraphExecutor):
        progresses: list[object] = []
        result = executor.execute(task, datetime.now().astimezone(), progresses.append)
        return result, progresses

    def _run_dir(self, run_id: str = "run-1") -> Path:
        return self.workspace / "test-case-graph" / run_id

    def test_runs_one_round_per_batch_and_carries_existing_graph(self) -> None:
        case_ids = [f"C{index:02d}" for index in range(1, GRAPH_BATCH_SIZE + 2)]
        payload = make_graph_input(case_ids)
        graph_text = json.dumps(GRAPH_WITH_EDGE, ensure_ascii=False)
        # 每轮都返回同一份累计图谱：第二轮因此必须以它作为 existing_graph。
        runner = _RecordingSkillRunner([graph_text, graph_text])
        executor = self._executor(runner)

        result, progresses = self._execute(self._task(payload), executor)

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(2, len(runner.calls))
        # 首轮历史为空，第二轮带上第一轮的产物。
        self.assertNotIn("E01", str(runner.calls[0]["input_text"]))
        self.assertIn("E01", str(runner.calls[1]["input_text"]))
        self.assertEqual(TEST_ORDER_GRAPH_SKILL_NAME, runner.calls[0]["skill_name"])
        # 每轮只带本批的 case_ids。
        first = _body_payload(runner.calls[0])
        second = _body_payload(runner.calls[1])
        self.assertEqual(
            [GRAPH_BATCH_SIZE],
            [len(link["case_ids"]) for link in first["case_requirement_links"]],
        )
        self.assertEqual([1], [len(link["case_ids"]) for link in second["case_requirement_links"]])
        self.assertEqual(
            case_ids[:GRAPH_BATCH_SIZE], first["case_requirement_links"][0]["case_ids"]
        )
        self.assertEqual(empty_graph(), first["existing_graph"])
        self.assertEqual(GRAPH_WITH_EDGE, second["existing_graph"])
        # 每轮请求文件与图谱都落盘，最终图谱落 resultYaml。
        self.assertTrue((self._run_dir() / "round-1-request.json").exists())
        self.assertTrue((self._run_dir() / "round-2-graph.json").exists())
        self.assertEqual(GRAPH_WITH_EDGE, json.loads(result.output_yaml))

        config = json.loads(result.intermediate_json_text)
        archive = config["graphRounds"]
        self.assertEqual(2, archive["roundCount"])
        self.assertEqual(2, archive["batchCount"])
        self.assertEqual([1, 1], [record["attempts"] for record in archive["rounds"]])
        # 回显必须保留 graphInput，前端据此渲染节点名。
        self.assertEqual(payload, config["graphInput"])
        summary = json.loads(result.result_summary_json)
        self.assertEqual(len(result.output_yaml), summary["graphLength"])
        self.assertEqual(1, summary["edgeCount"])
        # 成功后清理本任务临时用例副本，轮次归档保留。
        self.assertFalse((self._run_dir() / "run-1.json").exists())
        # 一次起始进度 + 每轮一次。
        self.assertEqual(1 + 2, len(progresses))

    def test_retries_round_with_validation_errors(self) -> None:
        payload = make_graph_input(["C01", "C02"])
        runner = _RecordingSkillRunner(
            ["这不是 JSON", json.dumps(GRAPH_WITH_EDGE, ensure_ascii=False)]
        )
        executor = self._executor(runner)

        result, _ = self._execute(self._task(payload), executor)

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(2, len(runner.calls))
        self.assertIn("未通过校验", str(runner.calls[1]["input_text"]))
        archive = json.loads(result.intermediate_json_text)["graphRounds"]
        self.assertEqual([2], [record["attempts"] for record in archive["rounds"]])

    def test_fails_after_attempts_exhausted_and_keeps_temp_files(self) -> None:
        payload = make_graph_input(["C01", "C02"])
        runner = _RecordingSkillRunner(["{}", "{}", "{}"])
        executor = self._executor(runner)

        result, progresses = self._execute(self._task(payload), executor)

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("图谱生成失败", str(result.error_message))
        self.assertEqual(3, len(runner.calls))
        # 失败保留临时文件，便于修复后重试。
        self.assertTrue((self._run_dir() / "run-1.json").exists())
        self.assertEqual("failed", progresses[-1].stage_status)
        archive = json.loads(result.intermediate_json_text)["graphRounds"]
        self.assertEqual(["failed"], [record["status"] for record in archive["rounds"]])

    def test_skips_cases_without_steps(self) -> None:
        payload = make_graph_input(["C01"])
        payload["cases"] = [make_case("C01"), make_case("C02", steps=False)]
        payload["case_requirement_links"] = [
            {"requirement_id": "REQ-001", "case_ids": ["C01", "C02"]}
        ]
        # C02 被跳过，因此本轮只剩 C01，图谱也只会是空图。
        runner = _RecordingSkillRunner([json.dumps(empty_graph())])

        result, _ = self._execute(self._task(payload), self._executor(runner))

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        request = json.loads((self._run_dir() / "round-1-request.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [["C01"]], [link["case_ids"] for link in request["case_requirement_links"]]
        )
        self.assertEqual(empty_graph(), request["existing_graph"])
        archive = json.loads(result.intermediate_json_text)["graphRounds"]
        self.assertEqual(["C02"], archive["skippedCaseIds"])
        summary = json.loads(result.result_summary_json)
        self.assertEqual(1, summary["skippedCaseCount"])

    def test_succeeds_with_empty_graph_when_nothing_to_analyze(self) -> None:
        payload = make_graph_input(["C01"])
        payload["case_requirement_links"] = []
        runner = _RecordingSkillRunner([])

        result, progresses = self._execute(self._task(payload), self._executor(runner))

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual([], runner.calls)
        self.assertEqual(empty_graph(), json.loads(result.output_yaml))
        archive = json.loads(result.intermediate_json_text)["graphRounds"]
        self.assertEqual(0, archive["roundCount"])
        self.assertEqual(1, len(progresses))

    def test_fails_when_skill_package_is_missing(self) -> None:
        payload = make_graph_input(["C01"])
        runner = _RecordingSkillRunner([])

        result, progresses = self._execute(
            self._task(payload), self._executor(runner, skill_dir_exists=False)
        )

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn(TEST_ORDER_GRAPH_SKILL_NAME, str(result.error_message))
        self.assertTrue(result.remediation)
        self.assertEqual([], runner.calls)
        self.assertEqual([], progresses)

    def test_execute_rejects_other_task_types(self) -> None:
        payload = make_graph_input(["C01"])
        task = self._task(payload)
        task.task_type = "functional_case_generate"

        result, progresses = self._execute(task, self._executor(_RecordingSkillRunner([])))

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual("不支持的任务类型: functional_case_generate", result.error_message)
        self.assertEqual([], progresses)

    def test_execute_fails_without_valid_input(self) -> None:
        task = self._task(make_graph_input(["C01"]))
        task.config_json = json.dumps({"graphInput": {"requirements": []}}, ensure_ascii=False)

        result, progresses = self._execute(task, self._executor(_RecordingSkillRunner([])))

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("cases", str(result.error_message))
        self.assertEqual([], progresses)


if __name__ == "__main__":
    unittest.main()
