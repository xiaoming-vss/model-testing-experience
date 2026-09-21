"""Test order graph executor.

图谱输入（需求 + 用例 + 需求用例关联）由控制端组装好放在 `configJson.graphInput` 里。
本执行器把用例写成任务独有的临时文件，按 case_ids 分批，逐轮调用
`update-test-case-graph` skill 增量累积图谱：每轮的产物作为下一轮的 `existing_graph`，
最终累计图谱落到 resultYaml。轮次的请求与产物留在任务目录里，平台只保留元信息与路径。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from testing_agent_ai_worker.config.models import NanobotConfig
from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.nanobot_runtime.config_builder import task_config_path
from testing_agent_ai_worker.nanobot_runtime.paths import (
    resolve_runtime_paths,
    resolve_task_workspace,
)
from testing_agent_ai_worker.nanobot_runtime.prompt import TEST_ORDER_GRAPH_JSON_ONLY_INSTRUCTION
from testing_agent_ai_worker.tasks.functional_case_generate.chain import run_skill_step
from testing_agent_ai_worker.tasks.functional_case_generate.summary import build_task_result_summary
from testing_agent_ai_worker.tasks.test_order_graph.rounds import (
    GRAPH_BATCH_SIZE,
    GRAPH_DIR_NAME,
    GRAPH_SCHEMA_VERSION,
    build_retry_suffix,
    build_round_body,
    empty_graph,
    parse_graph_text,
    split_batches,
    usable_cases,
    write_cases_file,
    write_round_graph,
    write_round_request,
)
from testing_agent_ai_worker.worker.runner import TaskExecutor

TEST_ORDER_GRAPH_TASK_TYPE = "test_order_graph"
# 与控制端 layout 的单阶段同名，进度和产物因此落在同一个阶段上。
GRAPH_STAGE = "generate"
TEST_ORDER_GRAPH_SKILL_NAME = "update-test-case-graph"
# 一轮内的调用次数上限：1 次生成 + 2 次带错误反馈的重试，仍失败则该轮失败。
ROUND_ATTEMPTS = 3
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


def _default_skill_dir_checker(workspace: Path, skill_name: str) -> bool:
    return (workspace / "skills" / skill_name).exists()


def _resolve_skill_result(result: Any) -> str:
    """兼容同步假实现和真实异步 nanobot 调用。"""

    if hasattr(result, "__await__"):
        return str(asyncio.run(result))
    return str(result)


class TestOrderGraphExecutor(TaskExecutor):
    """测试单测试图谱执行器。"""

    def __init__(
        self,
        *,
        nanobot_config: NanobotConfig,
        skill_runner: Callable[..., Any] = run_skill_step,
        skill_name: str = TEST_ORDER_GRAPH_SKILL_NAME,
        skill_dir_checker: Callable[[Path, str], bool] | None = None,
    ) -> None:
        self.nanobot_config = nanobot_config
        self.runtime_paths = resolve_runtime_paths(nanobot_config)
        self.skill_runner = skill_runner
        self.skill_name = skill_name
        self.skill_dir_checker = skill_dir_checker or _default_skill_dir_checker

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        if task.task_type != TEST_ORDER_GRAPH_TASK_TYPE:
            return self._result(
                task, started_at, TaskStatus.FAILED, f"不支持的任务类型: {task.task_type}"
            )
        try:
            payload = parse_graph_input(task.config_json)
        except GraphInputError as exc:
            return self._result(task, started_at, TaskStatus.FAILED, str(exc))

        workspace = resolve_task_workspace(self.nanobot_config, task)
        skill_dir = workspace / "skills" / self.skill_name
        if not self.skill_dir_checker(workspace, self.skill_name):
            return self._result(
                task,
                started_at,
                TaskStatus.FAILED,
                f"项目技能包未预置(缺少 {self.skill_name})",
                remediation="由部署侧按项目预置技能包后重新发起",
            )

        cases, skipped_case_ids = usable_cases(payload["cases"])
        usable_ids = {case["case_id"] for case in cases}
        batches = split_batches(payload["case_requirement_links"], usable_ids)
        archive: dict[str, Any] = {
            "batchSize": GRAPH_BATCH_SIZE,
            "batchCount": len(batches),
            "roundCount": 0,
            "skippedCaseIds": skipped_case_ids,
            "rounds": [],
        }
        progress_callback(self._progress(task, archive, status="running", error_message=None))

        if not batches:
            # 空批次合法：没有可分析的用例时返回空图谱，而不是判失败。
            return self._success(task, started_at, empty_graph(), archive, None)

        run_dir = workspace / GRAPH_DIR_NAME / task.run_id
        cases_path = write_cases_file(run_dir, task.run_id, cases)
        graph = empty_graph()
        with task_config_path(nanobot_config=self.nanobot_config, task=task) as config_path:
            for index, links in enumerate(batches, 1):
                round_graph, attempts, error = self._run_round(
                    task=task,
                    index=index,
                    links=links,
                    requirements=payload["requirements"],
                    cases_path=cases_path,
                    skill_dir=skill_dir,
                    config_path=config_path,
                    workspace=workspace,
                    existing_graph=graph,
                    allowed_case_ids=usable_ids,
                )
                record: dict[str, Any] = {
                    "round": index,
                    "caseIds": [case_id for link in links for case_id in link["case_ids"]],
                    "attempts": attempts,
                    "status": "failed" if error else "success",
                    "graphFile": "",
                    "edgeCount": len(round_graph.get("edges") or []),
                    "mainPathCount": len(round_graph.get("main_paths") or []),
                }
                archive["rounds"].append(record)
                archive["roundCount"] = len(archive["rounds"])
                if error is not None:
                    # 失败保留临时文件与已完成的轮次产物，便于修复后重试。
                    progress_callback(
                        self._progress(task, archive, status="failed", error_message=error)
                    )
                    return self._result(task, started_at, TaskStatus.FAILED, error, archive=archive)
                graph = round_graph
                record["graphFile"] = str(write_round_graph(run_dir, index, graph))
                progress_callback(
                    self._progress(task, archive, status="running", error_message=None)
                )

        # 全部批次完成：清理本任务临时用例副本，轮次归档保留。
        cases_path.unlink(missing_ok=True)
        return self._success(task, started_at, graph, archive, None)

    def _run_round(
        self,
        *,
        task: Task,
        index: int,
        links: list[dict[str, Any]],
        requirements: list[Any],
        cases_path: Path,
        skill_dir: Path,
        config_path: str,
        workspace: Path,
        existing_graph: dict[str, Any],
        allowed_case_ids: set[str],
    ) -> tuple[dict[str, Any], int, str | None]:
        """执行一轮：最多 ROUND_ATTEMPTS 次调用，失败时把校验错误反馈给模型重试。"""

        run_dir = cases_path.parent
        payload = {
            "requirements": requirements,
            "case_requirement_links": links,
            "case_file_path": str(cases_path),
            "existing_graph": existing_graph,
        }
        request_path = write_round_request(run_dir, index, payload)
        body = build_round_body(payload=payload, request_path=request_path, skill_dir=skill_dir)
        errors: list[str] = []
        for attempt in range(1, ROUND_ATTEMPTS + 1):
            prompt = body if not errors else body + build_retry_suffix(errors)
            try:
                raw = _resolve_skill_result(
                    self.skill_runner(
                        input_text=prompt,
                        session_key=f"{task.nanobot_session_key}-round-{index}",
                        skill_name=self.skill_name,
                        config_path=config_path,
                        workspace=str(workspace),
                        extra_instruction=TEST_ORDER_GRAPH_JSON_ONLY_INSTRUCTION,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 调用失败同样按轮重试
                errors = [f"调用失败：{exc}"]
                continue
            try:
                return parse_graph_text(raw, allowed_case_ids), attempt, None
            except Exception as exc:  # noqa: BLE001 - 结构不合法时带上原因重试
                errors = [f"{type(exc).__name__}: {exc}"]
        return empty_graph(), ROUND_ATTEMPTS, "图谱生成失败：" + "；".join(errors)

    def _progress(
        self,
        task: Task,
        archive: dict[str, Any],
        *,
        status: str,
        error_message: str | None,
    ) -> TaskProgress:
        return TaskProgress(
            task_id=task.task_id,
            run_id=task.run_id,
            current_stage=GRAPH_STAGE,
            stage_status="running" if status == "running" else "failed",
            intermediate_json_text=self._config_with_archive(task, archive),
            result_summary_json=self._summary(task, archive, status, error_message),
        )

    @staticmethod
    def _config_with_archive(task: Task, archive: dict[str, Any]) -> str:
        """回显 configJson 并附上轮次归档，保证 graphInput 仍在原位供平台读取。"""

        try:
            config = json.loads(task.config_json or "{}")
        except ValueError:
            config = {}
        if not isinstance(config, dict):
            config = {}
        config["graphRounds"] = archive
        return json.dumps(config, ensure_ascii=False)

    def _success(
        self,
        task: Task,
        started_at: datetime,
        graph: dict[str, Any],
        archive: dict[str, Any],
        error_message: str | None,
    ) -> TaskResult:
        graph_json = json.dumps(graph, ensure_ascii=False)
        archive["graphLength"] = len(graph_json)
        archive["edgeCount"] = len(graph.get("edges") or [])
        archive["mainPathCount"] = len(graph.get("main_paths") or [])
        return TaskResult(
            task_id=task.task_id,
            run_id=task.run_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.SUCCESS,
            intermediate_json_text=self._config_with_archive(task, archive),
            output_yaml=graph_json,
            result_summary_json=self._summary(task, archive, TaskStatus.SUCCESS, error_message),
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )

    def _result(
        self,
        task: Task,
        started_at: datetime,
        status: TaskStatus,
        error_message: str,
        *,
        archive: dict[str, Any] | None = None,
        remediation: str = "",
    ) -> TaskResult:
        return TaskResult(
            task_id=task.task_id,
            run_id=task.run_id,
            generate_task_id=task.generate_task_id,
            status=status,
            intermediate_json_text=(
                self._config_with_archive(task, archive)
                if archive is not None
                else task.config_json
            ),
            error_message=error_message,
            remediation=remediation,
            result_summary_json=self._summary(task, archive or {}, status, error_message),
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _summary(
        task: Task,
        archive: dict[str, Any],
        status: TaskStatus | str,
        error_message: str | None,
    ) -> str:
        details = {
            "graphLength": int(archive.get("graphLength") or 0),
            "batchCount": int(archive.get("batchCount") or 0),
            "roundCount": int(archive.get("roundCount") or 0),
            "edgeCount": int(archive.get("edgeCount") or 0),
            "mainPathCount": int(archive.get("mainPathCount") or 0),
            "skippedCaseCount": len(archive.get("skippedCaseIds") or []),
            "schemaVersion": GRAPH_SCHEMA_VERSION,
        }
        return build_task_result_summary(
            task=task,
            status=status,
            error_message=error_message,
            details=details,
        )
