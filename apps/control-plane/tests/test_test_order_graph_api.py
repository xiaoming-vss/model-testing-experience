"""测试单测试图谱：派发落库、并发闸门、输入校验、产物投影与删除链。"""

import asyncio
import json

from sqlalchemy import select
from support.function_case_library import make_sprint
from support.order_api import make_order
from support.project_api import account, project
from support.project_api import api as api

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.worker_task import WorkerTask

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
    attempt = query(
        api, select(AiGenerationAttempt).where(AiGenerationAttempt.execution_id == run["runId"])
    )[0]
    assert workers[0].run_id == attempt.id != run["runId"]
    assert workers[0].task_id
    assert workers[0].domain == "ai"


def test_graph_request_id_replays_and_rejects_changed_input(api):
    owner, pid, _, order_id = order_fixture(api, "graph-replay")
    connection_id = make_llm(api, owner, pid)
    url = f"/v1/test-orders/{order_id}/graph-analysis"
    payload = {
        "graphInput": GRAPH_INPUT,
        "connectionId": connection_id,
        "requestId": "graph-replay",
    }
    first = api.post(url, headers=owner, json=payload)
    assert first.status_code == 200, first.text
    replay = api.post(url, headers=owner, json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["runId"] == first.json()["data"]["runId"]
    changed = json.loads(json.dumps(GRAPH_INPUT))
    changed["requirements"][0]["requirement_title"] = "不同标题"
    assert api.post(url, headers=owner, json={**payload, "graphInput": changed}).status_code == 400


def test_worker_snapshot_carries_graph_task_id(api):
    owner, pid, _, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)
    run_id = dispatch(api, owner, order_id, connection_id).json()["data"]["runId"]

    async def load():
        from testing_agent.schemas.workers import WorkerClaimRequest
        from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService

        async with api.app.state.test_sessions() as session:
            attempt = await session.scalar(
                select(AiGenerationAttempt).where(AiGenerationAttempt.execution_id == run_id)
            )
            worker = await session.scalar(select(WorkerTask).where(WorkerTask.run_id == attempt.id))
            task = await session.scalar(
                select(AiGenerateTask).where(AiGenerateTask.task_type == "test_order_graph")
            )
            service = DirectStageWorkerService(session)
            await service.claim(worker, WorkerClaimRequest(worker_id="test-worker"))
            return await service.snapshot(worker), task.task_id, attempt.id

    payload, task_id, attempt_id = asyncio.run(load())
    # worker 端 run.taskId 必填：缺了它的快照整轮都领取不到任务。
    assert payload["run"]["taskId"] == task_id
    assert payload["run"]["attemptId"] == attempt_id != run_id


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
    attempts = query(
        api, select(AiGenerationAttempt).where(AiGenerationAttempt.execution_id.is_not(None))
    )
    assert len(attempts) == 1


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


def test_graph_history_supports_paged_summaries_and_details(api):
    owner, pid, _, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)
    before = api.get(f"/v1/test-orders/{order_id}/graph-analysis/runs", headers=owner)
    assert before.status_code == 200, before.text
    assert before.json()["data"]["total"] == 0
    run_id = dispatch(api, owner, order_id, connection_id).json()["data"]["runId"]
    response = api.get(f"/v1/test-orders/{order_id}/graph-analysis/runs", headers=owner)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] == 1
    assert response.json()["data"]["items"][0]["runId"] == run_id
    assert "configJson" not in response.json()["data"]["items"][0]
    detail = api.get(f"/v1/test-order-graph-runs/{run_id}", headers=owner)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["configJson"]["graphInput"] == GRAPH_INPUT


def test_graph_worker_lifecycle_keeps_old_success_when_later_run_fails(api):
    from testing_agent.api.deps import verify_worker_token

    owner, pid, _, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)
    api.app.dependency_overrides[verify_worker_token] = lambda: None

    def execute(status, content=None):
        run_response = dispatch(api, owner, order_id, connection_id)
        assert run_response.status_code == 200, run_response.text
        execution_id = run_response.json()["data"]["runId"]
        claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"})
        assert claim.status_code == 200, claim.text
        payload = claim.json()
        task_id, attempt_id = payload["taskId"], payload["attemptId"]
        assert execution_id != attempt_id
        base = f"/internal/ai-worker/tasks/{task_id}"
        snapshot = api.get(f"{base}/snapshot")
        assert snapshot.status_code == 200, snapshot.text
        assert snapshot.json()["run"]["attemptId"] == attempt_id
        started = api.post(f"{base}/started", json={"workerId": "worker", "attemptId": attempt_id})
        assert started.status_code == 204, started.text
        progress = api.patch(
            f"{base}/progress",
            json={
                "workerId": "worker",
                "attemptId": attempt_id,
                "currentStage": "generate",
                "stageStatus": "running",
                "resultSummaryJson": {"round": "discarded"},
            },
        )
        assert progress.status_code == 204, progress.text
        completed = api.post(
            f"{base}/completed",
            json={
                "workerId": "worker",
                "attemptId": attempt_id,
                "status": status,
                "resultYaml": content,
                "errorMessage": "later failure" if status == "failed" else "",
            },
        )
        assert completed.status_code == 204, completed.text
        return execution_id

    try:
        first = execute("success", json.dumps(graph_output()))
        second = execute("failed")
        history = api.get(f"/v1/test-orders/{order_id}/graph-analysis/runs", headers=owner).json()[
            "data"
        ]
        assert history["total"] == 2
        assert [item["runId"] for item in history["items"]] == [second, first]
        assert history["items"][0]["errorMessage"] == "later failure"
        old = api.get(f"/v1/test-order-graph-runs/{first}", headers=owner).json()["data"]
        assert json.loads(old["resultYaml"]) == graph_output()
        assert old["resultSummaryJson"] == {}
        assert api.delete(f"/v1/test-order-graph-runs/{second}", headers=owner).status_code == 200
        latest = api.get(f"/v1/test-orders/{order_id}/graph-analysis", headers=owner).json()["data"]
        assert latest["run"]["runId"] == first
        assert latest["run"]["configJson"]["graphInput"] == GRAPH_INPUT
    finally:
        api.app.dependency_overrides.pop(verify_worker_token, None)


def test_unified_graph_execution_detail_and_delete_respect_permissions(api):
    from testing_agent import models as m
    from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions
    from testing_agent.services.test_order_graph import build_graph_task

    owner, pid, _, order_id = order_fixture(api)
    _, viewer = account(api, "viewer-unified")
    _, stranger = account(api, "stranger-unified")
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "viewer-unified", "role": "viewer"},
        ).status_code
        == 200
    )

    async def seed():
        async with api.app.state.test_sessions() as session:
            order = await session.scalar(
                select(m.TestOrder).where(m.TestOrder.order_id == order_id)
            )
            project = await session.scalar(select(m.Project).where(m.Project.project_id == pid))
            task = build_graph_task(order, project.user_id)
            session.add(task)
            await session.flush()
            attempt, _ = await dispatch_auxiliary_execution(
                session,
                task=task,
                actor_id=project.user_id,
                request_id="unified-worker",
                execution_id="unified-run",
                connection_id="llm",
                source={"orderId": order_id},
                config={"graphInput": GRAPH_INPUT},
            )
            await session.commit()
            return attempt.id

    attempt_id = asyncio.run(seed())
    path = "/v1/test-order-graph-runs/unified-run"
    detail = api.get(path, headers=viewer)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["configJson"]["graphInput"] == GRAPH_INPUT
    assert api.get(path, headers=stranger).status_code in (403, 404)
    assert api.delete(path, headers=viewer).status_code == 403
    assert api.delete(path, headers=owner).status_code == 409

    async def complete():
        async with api.app.state.test_sessions() as session:
            attempt = await session.get(m.AiGenerationAttempt, attempt_id)
            queue = await session.scalar(
                select(WorkerTask).where(
                    WorkerTask.domain == "ai", WorkerTask.task_id == "unified-worker"
                )
            )
            await StageWorkerTransitions(session).completed(
                attempt.stage_id,
                attempt.id,
                queue.task_id,
                content=json.dumps(graph_output()),
                output_format="json",
                output_context=None,
            )
            queue.status = "success"
            await session.commit()

    asyncio.run(complete())
    assert api.delete(path, headers=owner).status_code == 200
    assert api.get(path, headers=owner).status_code == 404


def test_queued_graph_run_blocks_another_dispatch(api):
    owner, pid, _, order_id = order_fixture(api)
    connection_id = make_llm(api, owner, pid)
    run_id = dispatch(api, owner, order_id, connection_id).json()["data"]["runId"]

    async def set_queued():
        from sqlalchemy import update

        async with api.app.state.test_sessions() as session:
            await session.execute(
                update(AiGenerationAttempt)
                .where(AiGenerationAttempt.execution_id == run_id)
                .values(status="queued")
            )
            await session.commit()

    asyncio.run(set_queued())
    blocked = dispatch(api, owner, order_id, connection_id)
    assert blocked.status_code == 400
    assert "正在生成中" in blocked.text
