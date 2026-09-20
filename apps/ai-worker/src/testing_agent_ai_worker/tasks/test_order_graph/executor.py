"""Test order graph executor.

图谱输入（需求 + 用例 + 需求用例关联）由控制端组装好放在 `configJson.graphInput` 里，
这里只做输入校验、进度上报和结果交回。`cases[]` 的字段名与 skill 的输入契约一致，
所以接真实执行时可以直接投给 analyze-test-case-relations，不需要转换层。

执行过程目前是 mock：返回一份空图谱。接真实逻辑时只替换 `run_graph_analysis`。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.tasks.result_summary import build_task_result_summary
from testing_agent_ai_worker.worker.runner import TaskExecutor

TEST_ORDER_GRAPH_TASK_TYPE = "test_order_graph"
# 与控制端 layout 的单阶段同名，进度和产物因此落在同一个阶段上。
GRAPH_STAGE = "generate"
GRAPH_SCHEMA_VERSION = "2.0"
GRAPH_INPUT_LISTS = ("requirements", "cases", "case_requirement_links")


class GraphInputError(ValueError):
    """图谱输入不可用：属于输入侧问题，直接判失败，不做重试。"""


def parse_graph_input(config_json: str) -> dict[str, Any]:
    """取 `configJson.graphInput`；结构与控制端共用同一份契约。"""

    try:
        config = json.loads(config_json or "{}")
    except ValueError as exc:
        raise GraphInputError("configJson 不是合法 JSON") from exc
    if not isinstance(config, dict):
        raise GraphInputError("configJson 顶层必须是对象")
    payload = config.get("graphInput")
    if not isinstance(payload, dict):
        raise GraphInputError("configJson.graphInput 必须是对象")
    missing = [key for key in GRAPH_INPUT_LISTS if not isinstance(payload.get(key), list)]
    if missing:
        raise GraphInputError(f"图谱输入缺少数组字段：{'、'.join(missing)}")
    return payload


def graph_input_counts(payload: dict[str, Any]) -> dict[str, int]:
    return {
        "requirementCount": len(payload["requirements"]),
        "caseCount": len(payload["cases"]),
        "linkCount": len(payload["case_requirement_links"]),
    }


def run_graph_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    """执行图谱分析。

    当前为 mock：返回空图谱并把输入规模带出来，让整条链路（派发、进度、落库、读取）
    先跑通。真实的图谱执行逻辑定稿后只替换本函数。
    """

    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "main_paths": [],
        "edges": [],
        "mock": graph_input_counts(payload),
    }


class TestOrderGraphExecutor(TaskExecutor):
    """测试单测试图谱执行器。"""

    def __init__(self, analyze: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.analyze = analyze or run_graph_analysis

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        if task.task_type != TEST_ORDER_GRAPH_TASK_TYPE:
            return self._result(
                task, started_at, TaskStatus.FAILED, f"不支持的任务类型: {task.task_type}"
            )
        try:
            payload = parse_graph_input(task.config_json)
        except GraphInputError as exc:
            return self._result(task, started_at, TaskStatus.FAILED, str(exc))

        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                run_id=task.run_id,
                current_stage=GRAPH_STAGE,
                stage_status="running",
                intermediate_json_text=task.config_json,
                result_summary_json=self._summary(task, "running", "", None),
            )
        )

        graph = self.analyze(payload)
        graph_json = json.dumps(graph, ensure_ascii=False)
        return TaskResult(
            task_id=task.task_id,
            run_id=task.run_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.SUCCESS,
            # 回显整个 configJson，图谱输入因此留在 configJson.graphInput 里供平台读取。
            intermediate_json_text=task.config_json,
            output_yaml=graph_json,
            result_summary_json=self._summary(task, TaskStatus.SUCCESS, graph_json, None),
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _result(
        task: Task, started_at: datetime, status: TaskStatus, error_message: str
    ) -> TaskResult:
        return TaskResult(
            task_id=task.task_id,
            run_id=task.run_id,
            generate_task_id=task.generate_task_id,
            status=status,
            intermediate_json_text=task.config_json,
            error_message=error_message,
            result_summary_json=TestOrderGraphExecutor._summary(task, status, "", error_message),
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _summary(
        task: Task, status: TaskStatus | str, graph_json: str, error_message: str | None
    ) -> str:
        return build_task_result_summary(
            task=task,
            status=status,
            error_message=error_message,
            details={"graphLength": len(graph_json)},
        )
