"""测试单测试图谱：派发落库、并发闸门、输入校验、产物投影与删除链。"""

import asyncio
import json

from sqlalchemy import select
from test_ai_execution_storage import db as db
from test_ai_execution_storage import event, persist
from test_function_case_library import make_sprint
from test_project_membership_api import account, project
from test_project_membership_api import api as api
from test_test_order_api import make_order

from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.ai_execution import graph
from testing_agent.services.ai_execution import project as project_run

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
            "case_id": "case-1",
            "case_module": "系统配置",
            "case_title": "验证开关保存后刷新仍保持一致",
            "case_type": "配置相关",
            "priority": "2",
            "precondition": ["1. 已以管理员身份登录。"],
            "test_steps": ["1. 打开开关并保存。"],
            "expected_results": ["1. 保存成功。"],
        }
    ],
    "case_requirement_links": [{"requirement_id": "REQ-001", "case_ids": ["case-1"]}],
}


def graph_output():
    return {
        "schema_version": "2.0",
        "main_paths": [],
        "edges": [],
        "mock": {"requirementCount": 1, "caseCount": 1, "linkCount": 1},
    }


def make_llm(api, headers, pid):
    response = api.post(
        f"/v1/projects/{pid}/integrations/llm/connections",
        headers=headers,
        json={
            "name": "llm",
            "baseUrl": "https://llm.example/v1",
            "apiKey": "secret",
            "modelId": "model",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["connectionId"]


def dispatch(api, headers, order_id, connection_id, graph_input=None):
    return api.post(
        f"/v1/test-orders/{order_id}/graph-analysis",
        headers=headers,
        json={
            "graphInput": GRAPH_INPUT if graph_input is None else graph_input,
            "connectionId": connection_id,
        },
    )


def query(api, stmt):
    """在应用自己的会话里读一次，用于断言派发落库结果。"""

    async def run():
        async with api.app.state.test_sessions() as session:
            return list((await session.scalars(stmt)).all())

    return asyncio.run(run())


def order_fixture(api, name="owner"):
    _, owner = account(api, name)
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    order = make_order(api, owner, sprint_id, name="V2.3 回归")
    return owner, pid, sprint_id, order["orderId"]


def test_dispatch_records_graph_task_run_and_worker_task(api):
    owner, pid, sprint_id, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)

    response = dispatch(api, owner, order_id, connection_id)

    assert response.status_code == 200, response.text
    run = response.json()["data"]
    # 非需求域任务：需求留空，锚在测试单与测试单所属迭代上。
    assert run["requirementId"] == ""
    assert run["sprintId"] == sprint_id
    assert run["status"] == "pending"
    assert run["configJson"]["graphInput"] == GRAPH_INPUT

    tasks = query(api, select(AiGenerateTask).where(AiGenerateTask.task_type == "test_order_graph"))
    assert len(tasks) == 1
    assert tasks[0].order_id == order_id
    assert tasks[0].requirement_id == ""
    assert tasks[0].sprint_id == sprint_id

    workers = query(api, select(WorkerTask).where(WorkerTask.task_type == "test_order_graph"))
    assert len(workers) == 1
    assert workers[0].run_id == run["runId"]
    assert workers[0].task_id
    assert workers[0].domain == "ai"


def test_worker_snapshot_carries_graph_task_id(api):
    owner, pid, _, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)
    run_id = dispatch(api, owner, order_id, connection_id).json()["data"]["runId"]

    async def load():
        from testing_agent.services.worker import build_snapshot

        async with api.app.state.test_sessions() as session:
            worker = await session.scalar(select(WorkerTask).where(WorkerTask.run_id == run_id))
            task = await session.scalar(
                select(AiGenerateTask).where(AiGenerateTask.task_type == "test_order_graph")
            )
            return await build_snapshot(session, "ai", worker), task.task_id

    payload, task_id = asyncio.run(load())
    # worker 端 run.taskId 必填：缺了它的快照整轮都领取不到任务。
    assert payload["run"]["taskId"] == task_id
    assert payload["run"]["runId"] == run_id


def test_redispatch_reuses_task_and_blocks_while_running(api):
    owner, pid, _, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)

    assert dispatch(api, owner, order_id, connection_id).status_code == 200
    blocked = dispatch(api, owner, order_id, connection_id)

    assert blocked.status_code == 400, blocked.text
    assert "正在生成中" in blocked.text
    # 一张测试单只有一个图谱任务，重复派发只新增 run。
    tasks = query(api, select(AiGenerateTask).where(AiGenerateTask.task_type == "test_order_graph"))
    assert len(tasks) == 1
    runs = query(
        api, select(AiGenerateTaskRun).where(AiGenerateTaskRun.task_id == tasks[0].task_id)
    )
    assert len(runs) == 1


def test_dispatch_rejects_incomplete_graph_input(api):
    owner, pid, _, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)

    missing_link = {
        key: value for key, value in GRAPH_INPUT.items() if key != "case_requirement_links"
    }
    response = dispatch(api, owner, order_id, connection_id, missing_link)
    assert response.status_code == 400, response.text
    assert "case_requirement_links" in response.text

    no_cases = {**GRAPH_INPUT, "cases": []}
    response = dispatch(api, owner, order_id, connection_id, no_cases)
    assert response.status_code == 400, response.text
    assert "没有用例" in response.text

    assert query(api, select(AiGenerateTask).where(AiGenerateTask.order_id == order_id)) == []


def test_get_returns_latest_run_and_null_before_dispatch(api):
    owner, pid, _, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)

    before = api.get(f"/v1/test-orders/{order_id}/graph-analysis", headers=owner)
    assert before.status_code == 200, before.text
    assert before.json()["data"] == {"orderId": order_id, "run": None}

    dispatched = dispatch(api, owner, order_id, connection_id)
    assert dispatched.status_code == 200, dispatched.text

    after = api.get(f"/v1/test-orders/{order_id}/graph-analysis", headers=owner)
    assert after.status_code == 200, after.text
    latest = after.json()["data"]
    assert latest["orderId"] == order_id
    assert latest["run"]["runId"] == dispatched.json()["data"]["runId"]
    assert latest["run"]["configJson"]["graphInput"] == GRAPH_INPUT


def test_deleting_order_cascades_graph_task_and_sprint_still_deletes(api):
    owner, pid, sprint_id, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)
    assert dispatch(api, owner, order_id, connection_id).status_code == 200

    deleted = api.delete(f"/v1/test-orders/{order_id}", headers=owner)
    assert deleted.status_code == 200, deleted.text
    graph_tasks = select(AiGenerateTask).where(AiGenerateTask.task_type == "test_order_graph")
    assert query(api, graph_tasks) == []
    graph_workers = select(WorkerTask).where(WorkerTask.task_type == "test_order_graph")
    assert query(api, graph_workers) == []

    # 图谱任务是派生产物的容器：测试单删掉后它不残留，也不会挡住迭代删除。
    sprint_deleted = api.delete(f"/v1/sprints/{sprint_id}", headers=owner)
    assert sprint_deleted.status_code == 200, sprint_deleted.text


def test_worker_result_lands_in_result_yaml_without_review(db):
    task = AiGenerateTask(
        task_id="graph-task",
        task_type="test_order_graph",
        name="测试图谱",
        project_id="p",
        sprint_id="s",
        requirement_id="",
        order_id="order-1",
        creator_user_id="u",
        source_type="test_order_graph",
        source_content="",
        instruction="",
    )
    run = AiGenerateTaskRun(
        run_id="graph-run",
        task_id="graph-task",
        project_id="p",
        sprint_id="s",
        requirement_id="",
        trigger_user_id="u",
        status="pending",
        checkpoint_enabled=False,
        current_stage="generate",
        stage_status="pending",
        config_json={"graphInput": GRAPH_INPUT},
        snapshot_json={"orderId": "order-1"},
    )
    worker = WorkerTask(
        domain="ai",
        task_id="graph-worker",
        task_type="test_order_graph",
        run_id="graph-run",
        generate_task_id="graph-task",
        status="pending",
    )
    db.add_all([task, run, worker])
    db.flush()
    persist(db)
    db.commit()

    event(db, run, worker, status="success", stage="generate", output=json.dumps(graph_output()))

    stages, _ = graph(db, run)
    assert [stage.stage for stage in stages] == ["generate"]
    # 图谱是派生产物，不进人工审核。
    assert stages[0].review_status == "not_required"

    projected = project_run(db, run)
    # 产物落在 resultYaml，而不是 configJson 的某个键。
    assert json.loads(projected.result_yaml) == graph_output()
    # 图谱输入留在 configJson 里，前端据此渲染节点名。
    assert projected.config_json["graphInput"] == GRAPH_INPUT
