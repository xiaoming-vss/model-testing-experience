from __future__ import annotations

import json
import unittest
from datetime import datetime

from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import Task, TaskPayload
from testing_agent_ai_worker.tasks.test_order_graph.executor import (
    GRAPH_SCHEMA_VERSION,
    GraphInputError,
    TestOrderGraphExecutor,
    parse_graph_input,
    run_graph_analysis,
)

GRAPH_INPUT = {
    "requirements": [
        {
            "requirement_id": "REQ-001",
            "requirement_title": "本地清洗开关配置",
            "requirement_content": "管理员可以开启或关闭「启用本地清洗」开关。",
        }
    ],
    "cases": [
        {
            "case_id": "7d4c7339-971a-4784-9dfd-c8f79c330abf",
            "case_module": "系统配置",
            "case_title": "验证开关保存后刷新仍保持一致",
            "case_type": "配置相关",
            "priority": "2",
            "precondition": ["1. 已以管理员身份登录。"],
            "test_steps": ["1. 打开开关并保存。"],
            "expected_results": ["1. 保存成功。"],
        }
    ],
    "case_requirement_links": [
        {"requirement_id": "REQ-001", "case_ids": ["7d4c7339-971a-4784-9dfd-c8f79c330abf"]}
    ],
}


def _task(*, task_type: str = "test_order_graph", config: object | None = None) -> Task:
    return Task(
        task_id="task-1",
        run_id="run-1",
        generate_task_id="generate-1",
        task_type=task_type,
        project_id="project-1",
        sprint_id="sprint-1",
        config_json=json.dumps(
            {"graphInput": GRAPH_INPUT} if config is None else config, ensure_ascii=False
        ),
        payload=TaskPayload(openapi_content=""),
    )


class ParseGraphInputTest(unittest.TestCase):
    def test_reads_payload_from_config_json(self) -> None:
        self.assertEqual(GRAPH_INPUT, parse_graph_input(_task().config_json))

    def test_rejects_broken_config_json(self) -> None:
        with self.assertRaises(GraphInputError):
            parse_graph_input("{")

    def test_rejects_missing_graph_input(self) -> None:
        with self.assertRaises(GraphInputError):
            parse_graph_input(json.dumps({"requirementAnalysis": {}}))

    def test_names_the_missing_array_field(self) -> None:
        payload = {
            key: value for key, value in GRAPH_INPUT.items() if key != "case_requirement_links"
        }
        with self.assertRaises(GraphInputError) as raised:
            parse_graph_input(json.dumps({"graphInput": payload}))
        self.assertIn("case_requirement_links", str(raised.exception))


class RunGraphAnalysisTest(unittest.TestCase):
    def test_mock_returns_empty_graph_with_input_counts(self) -> None:
        graph = run_graph_analysis(GRAPH_INPUT)

        self.assertEqual(GRAPH_SCHEMA_VERSION, graph["schema_version"])
        self.assertEqual([], graph["main_paths"])
        self.assertEqual([], graph["edges"])
        self.assertEqual({"requirementCount": 1, "caseCount": 1, "linkCount": 1}, graph["mock"])


class TestOrderGraphExecutorTest(unittest.TestCase):
    def _execute(self, task: Task, executor: TestOrderGraphExecutor | None = None):
        progresses: list[object] = []
        result = (executor or TestOrderGraphExecutor()).execute(
            task, datetime.now().astimezone(), progresses.append
        )
        return result, progresses

    def test_execute_returns_mocked_graph_and_echoes_input(self) -> None:
        result, progresses = self._execute(_task())

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(GRAPH_SCHEMA_VERSION, json.loads(result.output_yaml)["schema_version"])
        self.assertEqual(1, len(progresses))
        self.assertEqual("generate", progresses[0].current_stage)
        # 图谱输入必须回显，平台据此把 configJson.graphInput 交给前端渲染节点名。
        self.assertEqual(GRAPH_INPUT, json.loads(result.intermediate_json_text)["graphInput"])
        summary = json.loads(result.result_summary_json)
        self.assertEqual("test_order_graph", summary["taskType"])
        self.assertEqual("success", summary["status"])
        self.assertEqual(len(result.output_yaml), summary["graphLength"])

    def test_execute_uses_injected_analyzer(self) -> None:
        graph = {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "main_paths": [],
            "edges": [],
            "custom": True,
        }
        result, _ = self._execute(_task(), TestOrderGraphExecutor(analyze=lambda _payload: graph))

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(graph, json.loads(result.output_yaml))

    def test_execute_rejects_other_task_types(self) -> None:
        result, progresses = self._execute(_task(task_type="functional_case_generate"))

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual("不支持的任务类型: functional_case_generate", result.error_message)
        self.assertEqual([], progresses)

    def test_execute_fails_without_valid_input(self) -> None:
        result, progresses = self._execute(_task(config={"graphInput": {"requirements": []}}))

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("cases", str(result.error_message))
        self.assertEqual([], progresses)


if __name__ == "__main__":
    unittest.main()
