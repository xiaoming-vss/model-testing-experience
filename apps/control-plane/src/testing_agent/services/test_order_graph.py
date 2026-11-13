"""测试单测试图谱：把外部接口组装好的图谱输入派发给 worker，产物落在该次 run 的 resultYaml 上。

图谱输入（需求 + 用例 + 需求用例关联）由调用方组装，平台原样转发，不做字段改名——
`cases[]` 的字段名与 worker 侧 skill 的输入契约一致，因此不需要转换层。
测试单内的用例与需求也可以直接由平台组装：见 `TestOrderGraphService.graph_input`。
"""

from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.domain.function_case_content import generation_fields
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.test_order import TestOrder
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.auxiliary_execution import lock_or_create_stage
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.repositories.test_order_entry import TestOrderEntryRepository
from testing_agent.schemas.test_order import TestOrderGraphInputResponse
from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution
from testing_agent.services.auxiliary_execution_view import auxiliary_detail, auxiliary_history
from testing_agent.services.common import dump
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.requirement_material_source import (
    approved_material,
    material_source,
)
from testing_agent.services.test_order import TestOrderService

TEST_ORDER_GRAPH_TASK_TYPE = task_type_for("test_order_graph")
# 新 kind 走 layout 的默认分支：单阶段 generate，且不在 FIELDS 里，产物因此落进 resultYaml。
TEST_ORDER_GRAPH_STAGE = "generate"
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


def _missing_material_message(names: list[str]) -> str:
    shown = "、".join(names[:5])
    if len(names) > 5:
        shown = f"{shown} 等 {len(names)} 条"
    return f"以下需求还没有审核通过的材料整理：{shown}"


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


def validate_graph_task_scope(task: AiGenerateTask | None, order: TestOrder) -> None:
    if task is not None and (
        task.order_id != order.order_id
        or task.project_id != order.project_id
        or task.sprint_id != order.sprint_id
        or task.requirement_id
        or task.task_type != TEST_ORDER_GRAPH_TASK_TYPE
    ):
        raise ErrNotFound()


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

    async def _read_order(self, user_id: str, order_id: str) -> TestOrder:
        order = await self.orders.get_accessible_entity(user_id, order_id, action="read")
        sprint = await self.orders.repository.get_sprint(order.sprint_id)
        if sprint is None or sprint.project_id != order.project_id:
            raise ErrNotFound()
        return order

    async def graph_input(self, user_id: str, order_id: str) -> dict[str, Any]:
        """组装该测试单的图谱输入：全部用例、本迭代的需求、需求到用例的关联。

        用例身份（模块 / 标题 / 类型 / 优先级）取用例当前值，正文取条目加入时的快照，
        与执行条目响应同一口径。需求不在测试单所属迭代的用例不算绑定需求，统一归入
        `requirement_id` 为 null 的分组；`requirements` 只含本迭代的需求。
        """

        order = await self._read_order(user_id, order_id)
        rows = await self.entries.list_order_cases_with_scope(order.order_id)
        cases: list[dict[str, Any]] = []
        requirements: list[dict[str, Any]] = []
        pending: list[tuple[dict[str, Any], str, str]] = []
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
                    item = {
                        "requirement_id": requirement.requirement_id,
                        "requirement_title": requirement.name,
                        "requirement_content": "",
                    }
                    requirements.append(item)
                    pending.append((item, requirement.requirement_id, requirement.name))
                link = {"requirement_id": group_id, "case_ids": []}
                by_group[group_id] = link
                links.append(link)
            link["case_ids"].append(case.case_id)
        await self._fill_material(pending)
        return dump(
            TestOrderGraphInputResponse,
            {
                "requirements": requirements,
                "cases": cases,
                "case_requirement_links": links,
            },
        )

    async def _fill_material(self, pending: list[tuple[dict[str, Any], str, str]]) -> None:
        """Fill each requirement's latest approved material; reject if any is missing."""
        chain = GenerationChainRepository(self.repository.session)
        missing: list[str] = []
        for item, requirement_id, name in pending:
            version = await approved_material(chain, requirement_id)
            if version is None:
                missing.append(name)
                continue
            item["requirement_content"] = material_source(version)
        if missing:
            raise dynamic_error(ErrBadRequest, _missing_material_message(missing))

    async def dispatch(self, user_id: str, order_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """派发一次图谱分析；一次生成完成前重复点击返回 400。"""

        await self.orders.get_accessible_entity(user_id, order_id, action="execute")
        # 调用方可以自行组装图谱输入（模块契约），平台只校验结构并原样转发。
        graph_input = require_graph_input(body.get("graph_input"))
        counts = graph_input_counts(graph_input)
        # End the initial authorization snapshot before waiting on the order lock.
        await self.repository.commit()
        order = await self.orders.repository.get_order_for_update(order_id)
        if order is None:
            raise ErrNotFound()
        sprint = await self.orders.ensure_sprint_access(user_id, order.sprint_id, action="execute")
        if sprint.project_id != order.project_id:
            raise ErrNotFound()
        task = await self.repository.get_task_by_order_type(
            order.order_id, TEST_ORDER_GRAPH_TASK_TYPE
        )
        if task is not None:
            task = await self.repository.get_task_for_update(task.task_id)
            if task is None:
                raise ErrNotFound()
        validate_graph_task_scope(task, order)
        from testing_agent.services.auxiliary_request import (
            find_replay,
            request_id,
            request_signature,
        )

        dispatch_id = request_id(body.get("request_id"), new_id())
        signature = request_signature(
            "test_order_graph",
            {"graphInput": graph_input, "connectionId": str(body.get("connection_id") or "")},
        )
        if task is not None and body.get("request_id") is not None:
            replay = await find_replay(
                self.repository.session,
                task=task,
                actor_id=user_id,
                request_id=dispatch_id,
                signature=signature,
            )
            if replay is not None:
                await self.repository.commit()
                if replay.execution_id is None:
                    raise ErrNotFound()
                return await auxiliary_detail(self.repository.session, replay.execution_id)
        latest = None
        if not str(body.get("connection_id") or "").strip():
            latest = await self._latest_unified(task)

        connection_id = await self._resolve_connection_id(user_id, body, order.project_id, latest)
        if task is None:
            task = build_graph_task(order, user_id)
            self.repository.add(task)
            await self.repository.session.flush()
        stage = await lock_or_create_stage(self.repository.session, task.task_id)
        if body.get("request_id") is not None:
            replay = await find_replay(
                self.repository.session,
                task=task,
                actor_id=user_id,
                request_id=dispatch_id,
                signature=signature,
                current_read=True,
                active_attempt_id=stage.active_attempt_id,
            )
            if replay is not None:
                await self.repository.commit()
                if replay.execution_id is None:
                    raise ErrNotFound()
                return await auxiliary_detail(self.repository.session, replay.execution_id)
        if stage.active_attempt_id:
            raise dynamic_error(ErrBadRequest, "图谱正在生成中，请等待完成后再试")
        run_id = new_id()
        attempt, _ = await dispatch_auxiliary_execution(
            self.repository.session,
            task=task,
            actor_id=user_id,
            request_id=dispatch_id,
            execution_id=run_id,
            connection_id=connection_id,
            source=build_graph_run_snapshot(order, run_id, task.task_id, counts, connection_id),
            config={"graphInput": graph_input},
            request_signature=signature,
        )
        await self.repository.commit()
        return await auxiliary_detail(self.repository.session, attempt.execution_id or run_id)

    async def get(self, user_id: str, order_id: str) -> dict[str, Any]:
        """返回该测试单最近一次图谱 run；从未生成过时 run 为 null。"""

        order = await self._read_order(user_id, order_id)
        task = await self.repository.get_task_by_order_type(
            order.order_id, TEST_ORDER_GRAPH_TASK_TYPE
        )
        validate_graph_task_scope(task, order)
        return {"orderId": order.order_id, "run": await self._latest_unified(task)}

    async def history(
        self, user_id: str, order_id: str, page: int, page_size: int
    ) -> dict[str, Any]:
        """Read bounded graph history after verifying the test-order scope."""
        order = await self._read_order(user_id, order_id)
        task = await self.repository.get_task_by_order_type(
            order.order_id, TEST_ORDER_GRAPH_TASK_TYPE
        )
        validate_graph_task_scope(task, order)
        if task is not None:
            return await auxiliary_history(self.repository.session, task.task_id, page, page_size)
        if page < 1 or not 1 <= page_size <= 100:
            raise ErrBadRequest()
        return {
            "items": [],
            "total": 0,
            "statusCounts": {},
            "reviewPendingCount": 0,
            "latestRun": None,
        }

    async def _latest_unified(self, task: AiGenerateTask | None) -> dict[str, Any] | None:
        if task is None:
            return None
        history = await auxiliary_history(self.repository.session, task.task_id, 1, 1)
        latest = history["latestRun"]
        if latest is None:
            return None
        return await auxiliary_detail(self.repository.session, latest["runId"])

    async def _resolve_connection_id(
        self,
        user_id: str,
        body: dict[str, Any],
        project_id: str,
        latest: dict[str, Any] | None,
    ) -> str:
        """本次指定的连接优先，其次沿用上一次派发用过的连接。"""

        connection_id = str(body.get("connection_id") or "").strip()
        if not connection_id and latest is not None:
            connection_id = str((latest.get("snapshotJson") or {}).get("llmConnectionId") or "")
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
