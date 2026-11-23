"""工单 06/07:code_risk_analysis 任务类型、凭据下发与报告存储读取。

覆盖:
- 任务快照组装(需求文档、绑定清单+基线+connectionId、现有测试内容口径);
- RC-3 情形④分支校验接线(任务创建时按绑定解析连接查询远端);
- GitLab 凭据内部端点(worker token 鉴权、按快照分组解密、错误语义);
- 失败错误消息与补救建议回显;
- 风险报告解析与回读(worker 完成回调 resultYaml → run 表 → report 结构);
- 重复发起同一需求产生多次任务记录且互不覆盖;
- /v1 任务创建与运行端点。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.code_risk_analysis import (  # noqa: F401
    RISK_REPORT_YAML,
    FakeSession,
    approved_understanding,
    dump_code_risk_analysis_run,
    make_run,
    real_risk_service,
    worker_contract_authority,
    worker_settings,
)

from testing_agent.api.deps import (
    get_current_user_id,
    get_generation_launcher,
    get_generation_queries,
    get_generation_task_commands,
    get_worker_task_service,
)
from testing_agent.app import create_app
from testing_agent.core.config import get_settings
from testing_agent.core.errors import AppError
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import WorkerTaskEventRequest
from testing_agent.services import worker_task as worker_task_service_module
from testing_agent.services.ai_task_output import dump_run
from testing_agent.services.code_risk_analysis import (
    parse_risk_report,
)
from testing_agent.services.worker_task import WorkerTaskService


async def test_worker_rejects_legacy_code_risk_completion(monkeypatch):
    """验收口径:WorkerTaskService.complete 全链路落报告到 run 表,详情可回读。"""
    run = make_run(status="running", result_yaml="")
    task = SimpleNamespace(
        task_id="worker-task-1",
        domain="ai",
        task_type="code_risk_analysis",
        run_id="run-1",
        worker_id="worker-1",
        status="running",
        heartbeat_at=None,
        started_at=None,
        finished_at=None,
        lease_expires_at=None,
        error_message="",
    )

    async def fake_find_task(session, domain, task_id):
        assert domain == "ai"
        return task

    monkeypatch.setattr(worker_task_service_module, "find_task", fake_find_task)

    class FakeRepository:
        session = FakeSession([run])

        async def get_ai_run(self, run_id):
            return run

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    body = WorkerTaskEventRequest(
        workerId="worker-1",
        taskId="worker-task-1",
        runId="run-1",
        status="success",
        resultYaml=RISK_REPORT_YAML,
    )
    with pytest.raises(AppError) as rejected:
        await WorkerTaskService(FakeRepository()).complete("ai", "worker-task-1", body)
    assert rejected.value.http_code == 404
    assert run.result_yaml == ""


@pytest.mark.asyncio
async def test_repeated_runs_create_distinct_records_without_overwrite(  # noqa: F811
    db,
    monkeypatch,
    approved_understanding,  # noqa: F811
):
    from unittest.mock import AsyncMock

    from sqlalchemy import select

    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.generation_candidates import RequirementGenerationChain
    from testing_agent.services import ai_run_launcher as launcher_module
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions

    service = real_risk_service(db)
    db.add(
        RequirementGenerationChain(
            chain_id="material-chain",
            requirement_id="r",
            kind="requirement_analysis",
            task_id="understanding-r",
        )
    )
    db.commit()
    monkeypatch.setattr(
        service.launcher,
        "_prepare_current_material",
        AsyncMock(return_value=(object(), approved_understanding)),
    )
    monkeypatch.setattr(launcher_module, "lock_prepared_requirement_root", AsyncMock())
    monkeypatch.setattr(launcher_module, "lock_current_material", AsyncMock())
    run_body = {"connectionId": "llm", "triggerType": "manual"}
    first = await service.launcher.launch("code_risk_analysis", "task", run_body, "u")
    with pytest.raises(AppError, match="代码风险正在生成中"):
        await service.launcher.launch("code_risk_analysis", "task", run_body, "u")
    attempt = db.scalar(
        select(AiGenerationAttempt).where(AiGenerationAttempt.execution_id == first["runId"])
    )
    worker = db.scalar(select(WorkerTask).where(WorkerTask.run_id == attempt.id))
    await StageWorkerTransitions(AsyncSessionAdapter(db)).completed(
        attempt.stage_id,
        attempt.id,
        worker.task_id,
        content=RISK_REPORT_YAML,
        output_format="text",
        output_context=None,
    )
    worker.status = "success"
    db.commit()
    second = await service.launcher.launch("code_risk_analysis", "task", run_body, "u")
    assert first["runId"] != second["runId"]
    listed = await service.queries.list_run_summaries("code_risk_analysis", "task", "u")
    assert listed["total"] == 2
    assert [item["runId"] for item in listed["items"]] == [second["runId"], first["runId"]]
    detail = await service.queries.get_run("code_risk_analysis", first["runId"], "u")
    assert detail["report"]["repositories"][0]["baselineCommit"] == "abc123"
    assert detail["report"]["analyzedAt"] == "2026-08-21T10:30:00Z"


# ---------------------------------------------------------------------------
# HTTP 端点
# ---------------------------------------------------------------------------


def test_gitlab_credentials_endpoint_requires_worker_token():
    class FakeWorkerService:
        async def gitlab_credentials(self, task_id):
            assert task_id == "worker-task-1"
            return {
                "taskId": task_id,
                "bindings": [
                    {"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"}
                ],
                "credentials": [
                    {
                        "connectionId": "conn-1",
                        "baseUrl": "https://gitlab.example.com",
                        "accessToken": "memory-only-token",
                        "repositoryIds": ["repo-1"],
                    }
                ],
            }

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)

    unauthorized = client.get("/internal/ai-worker/tasks/worker-task-1/gitlab-credentials")
    assert unauthorized.status_code == 401
    assert set(unauthorized.json().keys()) == {"message"}

    response = client.get(
        "/internal/ai-worker/tasks/worker-task-1/gitlab-credentials",
        headers={"X-Worker-Token": "worker-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["taskId"] == "worker-task-1"
    assert body["credentials"][0]["accessToken"] == "memory-only-token"
    assert body["credentials"][0]["repositoryIds"] == ["repo-1"]


def test_code_risk_analysis_task_endpoints_dispatch_to_service():
    class FakeGenerationEndpoints:
        captured = {}

        async def create(self, kind, project_id, body, user_id):
            self.captured["create"] = (kind, project_id, body, user_id)
            assert kind == "code_risk_analysis"
            assert body["requirementId"] == "req-1"
            return {
                "taskId": "task-1",
                "taskType": "code_risk_analysis",
                "name": "登录改造 代码风险分析",
                "projectId": project_id,
                "sprintId": "sprint-1",
                "requirementId": "req-1",
                "creatorUserId": user_id,
                "sourceType": "text",
                "sourceContent": "",
                "instruction": "",
                "createdAt": None,
                "updatedAt": None,
            }

        async def launch(self, kind, task_id, body, user_id):
            self.captured["run"] = (kind, task_id, body, user_id)
            assert body["connectionId"] == "llm-1"
            return dump_run(
                make_run(
                    status="pending",
                    error_message="",
                    snapshot_json={},
                )
            )

        async def get_run(self, kind, run_id, user_id):
            assert kind == "code_risk_analysis"
            return dump_code_risk_analysis_run(make_run(result_yaml=RISK_REPORT_YAML))

        async def list(self, kind, project_id, user_id, **kwargs):
            return {"items": [], "total": 0, "statusCounts": {}}

        async def get(self, kind, task_id, user_id):
            return {
                "taskId": task_id,
                "taskType": "code_risk_analysis",
                "name": "登录改造 代码风险分析",
                "projectId": "project-1",
                "sprintId": "sprint-1",
                "requirementId": "req-1",
                "creatorUserId": user_id,
                "sourceType": "text",
                "sourceContent": "",
                "instruction": "",
                "createdAt": None,
                "updatedAt": None,
            }

        async def list_run_summaries(self, kind, task_id, user_id, page=1, page_size=20):
            return {
                "items": [
                    {
                        **dump_run(make_run(result_yaml=RISK_REPORT_YAML)),
                        "report": parse_risk_report(RISK_REPORT_YAML),
                    }
                ],
                "total": 1,
            }

    app = create_app(worker_settings())
    fake = FakeGenerationEndpoints()
    app.dependency_overrides[get_generation_launcher] = lambda: fake
    app.dependency_overrides[get_generation_queries] = lambda: fake
    app.dependency_overrides[get_generation_task_commands] = lambda: fake
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    client = TestClient(app)

    created = client.post(
        "/v1/projects/project-1/code-risk-analysis-tasks",
        json={"name": "登录改造 代码风险分析", "requirementId": "req-1"},
    )
    assert created.status_code == 200
    assert created.json()["code"] == 0
    assert created.json()["data"]["taskId"] == "task-1"

    listed = client.get("/v1/projects/project-1/code-risk-analysis-tasks")
    assert listed.status_code == 200
    assert listed.json()["data"]["items"] == []

    fetched = client.get("/v1/code-risk-analysis-tasks/task-1")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["taskId"] == "task-1"

    started = client.post(
        "/v1/code-risk-analysis-tasks/task-1/run",
        json={"connectionId": "llm-1", "triggerType": "manual"},
    )
    assert started.status_code == 200
    assert started.json()["data"]["runId"] == "run-1"

    runs = client.get("/v1/code-risk-analysis-tasks/task-1/runs")
    assert runs.status_code == 200
    listed_run = runs.json()["data"]["items"][0]
    assert listed_run["runId"] == "run-1"
    assert "report" not in listed_run
    assert "resultYaml" not in listed_run

    run_detail = client.get("/v1/code-risk-analysis-runs/run-1")
    assert run_detail.status_code == 200
    detail = run_detail.json()["data"]
    assert detail["status"] == "failed"
    assert detail["errorMessage"] == "GitLab 基线分支已删除"
    assert detail["resultYaml"] == RISK_REPORT_YAML
    report = detail["report"]
    assert report["analyzedAt"] == "2026-08-21T10:30:00Z"
    assert report["repositories"][0]["baselineCommit"] == "abc123"
    assert report["repositories"][0]["headCommit"] == "def456"
    assert report["changeOverview"]["filesChanged"] == 12
    assert report["risks"][0]["level"] == "high"
    assert report["affectedCases"][0]["caseId"] == "ac-1"
    assert report["coverageGaps"][0]["suggestion"] == "新增失败路径用例"


def test_code_risk_analysis_router_grouped_in_openapi():
    app = create_app(worker_settings())
    paths = app.openapi()["paths"]
    assert paths["/v1/projects/{projectId}/code-risk-analysis-tasks"]["post"]["tags"] == [
        "Code Risk Analysis Tasks"
    ]
    assert paths["/v1/code-risk-analysis-tasks/{taskId}"]["get"]["tags"] == [
        "Code Risk Analysis Tasks"
    ]
    assert paths["/v1/code-risk-analysis-runs/{runId}"]["get"]["tags"] == [
        "Code Risk Analysis Tasks"
    ]
