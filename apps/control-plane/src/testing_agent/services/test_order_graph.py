"""测试单测试图谱：把外部接口组装好的图谱输入派发给 worker，产物落在该次 run 的 resultYaml 上。

图谱输入（需求 + 用例 + 需求用例关联）由调用方组装，平台原样转发，不做字段改名——
`cases[]` 的字段名与 worker 侧 skill 的输入契约一致，因此不需要转换层。
测试单内的用例与需求也可以直接由平台组装：见 `TestOrderGraphService.graph_input`。
"""

from __future__ import annotations

from typing import Any

from testing_agent.core.enums import RunStatus, StageStatus
from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.core.sid import new_id
from testing_agent.domain.function_case_content import generation_fields
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.test_order import TestOrder
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.test_order_entry import TestOrderEntryRepository
from testing_agent.schemas.test_order import TestOrderGraphInputResponse
from testing_agent.services.ai_generate_task import (
    dump_run,
    requirement_source_content,
    task_type_for,
)
from testing_agent.services.common import dump
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.test_order import TestOrderService

TEST_ORDER_GRAPH_TASK_TYPE = task_type_for("test_order_graph")
# 新 kind 走 layout 的默认分支：单阶段 generate，且不在 FIELDS 里，产物因此落进 resultYaml。
TEST_ORDER_GRAPH_STAGE = "generate"
TEST_ORDER_GRAPH_DISPATCH_STATUSES = {
    RunStatus.PENDING.value,
    RunStatus.CLAIMED.value,
    RunStatus.RUNNING.value,
}
GRAPH_INPUT_LISTS = ("requirements", "cases", "case_requirement_links")


def require_graph_input(payload: Any) -> dict[str, Any]:
    """校验图谱输入结构；原样返回，不重写内部字段名。"""

    if not isinstance(payload, dict):
        raise dynamic_error(ErrBadRequest, "图谱输入必须是对象")
    missing = [key for key in GRAPH_INPUT_LISTS if not isinstance(payload.get(key), list)]
    if missing:
        raise dynamic_error(ErrBadRequest, f"图谱输入缺少数组字段：{'、'.join(missing)}")
    if not payload["cases"]:
        raise dynamic_error(ErrBadRequest, "图谱输入没有用例")
    return payload


def graph_input_counts(graph_input: dict[str, Any]) -> dict[str, int]:
    return {
        "requirementCount": len(graph_input["requirements"]),
        "caseCount": len(graph_input["cases"]),
        "linkCount": len(graph_input["case_requirement_links"]),
    }


def build_graph_run_snapshot(
    order: TestOrder,
    run_id: str,
    task_id: str,
    counts: dict[str, int],
    connection_id: str,
) -> dict[str, Any]:
    """派发快照只记归属与输入规模；图谱输入本体在 configJson.graphInput。

    `taskId` 是 worker 端快照协议的必填项（与生成类快照同一口径），缺了 worker 解析
    快照就会失败。
    """

    return {
        "taskId": task_id,
        "taskType": TEST_ORDER_GRAPH_TASK_TYPE,
        "runId": run_id,
        "projectId": order.project_id,
        "sprintId": order.sprint_id,
        "orderId": order.order_id,
        "orderName": order.name,
        "llmConnectionId": connection_id,
        **counts,
    }


def build_graph_task(order: TestOrder, user_id: str) -> AiGenerateTask:
    """非需求域任务：requirement_id 留空，锚在测试单上（与测试报告任务同一口径）。"""

    name = str(order.name or "").strip()
    return AiGenerateTask(
        task_id=new_id(),
        task_type=TEST_ORDER_GRAPH_TASK_TYPE,
        name=f"{name} 测试图谱" if name else "测试图谱",
        project_id=order.project_id,
        sprint_id=order.sprint_id,
        requirement_id="",
        order_id=order.order_id,
        creator_user_id=user_id,
        source_type=TEST_ORDER_GRAPH_TASK_TYPE,
        source_content="",
        instruction="",
    )


class TestOrderGraphService:
    def __init__(
        self,
        repository: AiGenerateTaskRepository,
        test_order_service: TestOrderService,
        entries: TestOrderEntryRepository,
    ) -> None:
        self.repository = repository
        self.orders = test_order_service
        self.entries = entries

    async def graph_input(self, user_id: str, order_id: str) -> dict[str, Any]:
        """组装该测试单的图谱输入：全部用例、本迭代的需求、需求到用例的关联。

        用例身份（模块 / 标题 / 类型 / 优先级）取用例当前值，正文取条目加入时的快照，
        与执行条目响应同一口径。需求不在测试单所属迭代的用例不算绑定需求，统一归入
        `requirement_id` 为 null 的分组；`requirements` 只含本迭代的需求。
        """

        order = await self.orders.get_accessible_entity(user_id, order_id, action="read")
        rows = await self.entries.list_order_cases_with_scope(order.order_id)
        cases: list[dict[str, Any]] = []
        requirements: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        by_group: dict[str | None, dict[str, Any]] = {}
        for entry, case, _suite, requirement in rows:
            cases.append(
                {
                    "case_id": case.case_id,
                    "case_module": case.module,
                    "case_title": case.title,
                    "case_type": case.case_type,
                    "priority": case.priority,
                    **generation_fields(entry.snapshot_json or {}),
                }
            )
            in_iteration = requirement.sprint_id == order.sprint_id
            group_id = requirement.requirement_id if in_iteration else None
            link = by_group.get(group_id)
            if link is None:
                if in_iteration:
                    requirements.append(
                        {
                            "requirement_id": requirement.requirement_id,
                            "requirement_title": requirement.name,
                            "requirement_content": requirement_source_content(requirement),
                        }
                    )
                link = {"requirement_id": group_id, "case_ids": []}
                by_group[group_id] = link
                links.append(link)
            link["case_ids"].append(case.case_id)
        return dump(
            TestOrderGraphInputResponse,
            {
                "requirements": requirements,
                "cases": cases,
                "case_requirement_links": links,
            },
        )

    async def dispatch(self, user_id: str, order_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """派发一次图谱分析；一次生成完成前重复点击返回 400。"""

        order = await self.orders.get_accessible_entity(user_id, order_id, action="execute")
        graph_input = require_graph_input(body.get("graph_input"))
        counts = graph_input_counts(graph_input)
        task = await self.repository.get_task_by_order_type(
            order.order_id, TEST_ORDER_GRAPH_TASK_TYPE
        )
        latest = await self._latest_run(task)
        if latest is not None and latest.status in TEST_ORDER_GRAPH_DISPATCH_STATUSES:
            raise dynamic_error(ErrBadRequest, "图谱正在生成中，请等待完成后再试")

        connection_id = await self._resolve_connection_id(user_id, body, order.project_id, latest)
        if task is None:
            task = build_graph_task(order, user_id)
            self.repository.add(task)
        run_id = new_id()
        run = AiGenerateTaskRun(
            run_id=run_id,
            task_id=task.task_id,
            requirement_id="",
            sprint_id=order.sprint_id,
            project_id=order.project_id,
            trigger_user_id=user_id,
            trigger_type="manual",
            status=RunStatus.PENDING.value,
            checkpoint_enabled=False,
            current_stage=TEST_ORDER_GRAPH_STAGE,
            stage_status=StageStatus.PENDING.value,
            snapshot_json=build_graph_run_snapshot(
                order, run_id, task.task_id, counts, connection_id
            ),
            config_json={"graphInput": graph_input},
            result_summary_json={},
        )
        self.repository.add(
            WorkerTask(
                domain="ai",
                task_id=new_id(),
                task_type=TEST_ORDER_GRAPH_TASK_TYPE,
                run_id=run_id,
                generate_task_id=task.task_id,
                llm_connection_id=connection_id,
                status=RunStatus.PENDING.value,
            )
        )
        self.repository.add(run)
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def get(self, user_id: str, order_id: str) -> dict[str, Any]:
        """返回该测试单最近一次图谱 run；从未生成过时 run 为 null。"""

        order = await self.orders.get_accessible_entity(user_id, order_id, action="read")
        task = await self.repository.get_task_by_order_type(
            order.order_id, TEST_ORDER_GRAPH_TASK_TYPE
        )
        latest = await self._latest_run(task)
        return {
            "orderId": order.order_id,
            "run": dump_run(latest) if latest is not None else None,
        }

    async def _latest_run(self, task: AiGenerateTask | None):
        if task is None:
            return None
        runs = await self.repository.list_runs(task.task_id)
        return runs[0] if runs else None

    async def _resolve_connection_id(
        self,
        user_id: str,
        body: dict[str, Any],
        project_id: str,
        latest: Any,
    ) -> str:
        """本次指定的连接优先，其次沿用上一次派发用过的连接。"""

        connection_id = str(body.get("connection_id") or "").strip()
        if not connection_id and latest is not None:
            previous = await self.repository.get_latest_worker_task_by_run_id(latest.run_id)
            connection_id = str(getattr(previous, "llm_connection_id", "") or "")
        connection = await require_personal_connection(
            self.repository.session, user_id, "llm", connection_id, project_id
        )
        return connection.connection_id


__all__ = [
    "GRAPH_INPUT_LISTS",
    "TEST_ORDER_GRAPH_STAGE",
    "TEST_ORDER_GRAPH_TASK_TYPE",
    "TestOrderGraphService",
    "build_graph_run_snapshot",
    "build_graph_task",
    "graph_input_counts",
    "require_graph_input",
]
