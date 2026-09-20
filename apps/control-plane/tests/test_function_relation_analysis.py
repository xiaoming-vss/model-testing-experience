"""按钮触发的图谱分析：派发闸门、worker 输入快照与产物投影。"""

import json

import pytest
from sqlalchemy import select

from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.ai_execution import graph, persist, project
from tests.test_ai_execution_storage import (
    AsyncSessionAdapter,
    create_run,
    event,
)
from tests.test_ai_execution_storage import db as db


def cases_output():
    return json.dumps(
        {
            "cases": [
                {
                    "case_id": f"case-{index}",
                    "case_module": "任务管理",
                    "case_title": f"用例{index}",
                    "case_type": "功能测试",
                    "priority": "1",
                    "precondition": ["1. 准备就绪"],
                    "test_steps": ["1. 提交任务"],
                    "expected_results": ["1. 任务成功"],
                }
                for index in range(1, 4)
            ]
        },
        ensure_ascii=False,
    )


def relations_output():
    return {
        "schema_version": "2.0",
        "main_paths": [{"path_id": "P01", "case_ids": ["case-1", "case-2", "case-3"]}],
        "edges": [
            {
                "edge_id": f"E0{index}",
                "from_case_id": f"case-{index}",
                "to_case_id": f"case-{index + 1}",
                "relation_type": "next",
                "order": 1,
            }
            for index in (1, 2)
        ],
    }


def approve(db, run):
    run.review_status = "approved"
    run.reviewer_user_id = "u"
    from datetime import UTC, datetime

    run.reviewed_at = datetime.now(UTC)
    persist(db)
    db.commit()


@pytest.mark.asyncio
async def test_relation_dispatch_requires_approved_review(db):
    from testing_agent.core.errors import AppError
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_generate_task import AiGenerateTaskService

    run, worker = create_run(db)
    event(db, run, worker, status="success", stage="completed", output=cases_output())
    service = AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    with pytest.raises(AppError, match="审核通过"):
        await service.generate_relation_analysis("run", None, "u")


@pytest.mark.asyncio
async def test_relation_dispatch_requires_platform_case_ids(db):
    from testing_agent.core.errors import AppError
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_generate_task import AiGenerateTaskService

    run, worker = create_run(db)
    event(
        db,
        run,
        worker,
        status="success",
        stage="completed",
        output=json.dumps({"cases": [{"case_module": "任务管理"}]}),
    )
    approve(db, run)
    service = AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    with pytest.raises(AppError, match="case_id"):
        await service.generate_relation_analysis("run", None, "u")


@pytest.mark.asyncio
async def test_relation_dispatch_prepares_worker_input(db):
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_generate_task import AiGenerateTaskService
    from testing_agent.services.worker import build_snapshot

    run, first = create_run(db)
    event(
        db,
        run,
        first,
        status="success",
        stage="completed",
        output=cases_output(),
        config={"requirementAnalysis": {"functionalOverview": {}}},
    )
    approve(db, run)
    service = AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    result = await service.generate_relation_analysis("run", None, "u")

    assert result["currentStage"] == "relation_analysis"
    assert result["status"] == "pending"
    assert result["reviewStatus"] == "approved"
    assert result["resultYaml"] == cases_output()

    graph_worker = db.scalar(
        select(WorkerTask)
        .where(WorkerTask.run_id == "run")
        .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
    )
    assert graph_worker.task_id != first.task_id
    assert graph_worker.status == "pending"

    # worker 快照输入 = 派发快照：原始需求 + 需求分析 + 带 case_id 的完整用例。
    payload = await build_snapshot(AsyncSessionAdapter(db), "ai", graph_worker)
    snapshot_task = payload["run"]
    config = json.loads(payload["configJson"])
    assert snapshot_task["sourceContent"] == "sample"
    assert config["requirementAnalysis"] == {"functionalOverview": {}}
    dispatched_cases = json.loads(config["resultYaml"])["cases"]
    assert [case["case_id"] for case in dispatched_cases] == ["case-1", "case-2", "case-3"]


@pytest.mark.asyncio
async def test_relation_completion_projects_case_relations(db):
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_generate_task import AiGenerateTaskService

    run, first = create_run(db)
    event(
        db,
        run,
        first,
        status="success",
        stage="completed",
        output=cases_output(),
        config={"requirementAnalysis": {"functionalOverview": {}}},
    )
    approve(db, run)
    service = AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    await service.generate_relation_analysis("run", None, "u")
    graph_worker = db.scalar(
        select(WorkerTask)
        .where(WorkerTask.run_id == "run")
        .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
    )

    # 图谱任务完成事件：current_stage 回到 completed，产物只进 configJson。
    event(
        db,
        run,
        graph_worker,
        status="success",
        stage="completed",
        config={
            "requirementAnalysis": {"functionalOverview": {}},
            "caseNames": None,
            "caseRelations": relations_output(),
        },
    )
    project(db, run)
    assert run.current_stage == "completed"
    assert run.status == "success"
    assert run.config_json["caseRelations"] == relations_output()
    assert run.result_yaml == cases_output()

    stages, attempts = graph(db, run)
    relation = next(s for s in stages if s.stage == "relation_analysis")
    detailed = next(s for s in stages if s.stage == "detailed_cases")
    assert relation.execution_status == "success"
    assert relation.review_status == "not_required"
    relation_attempt = attempts[relation.current_artifact_attempt_id]
    assert relation_attempt.worker_task_id == graph_worker.task_id
    assert json.loads(relation_attempt.output_content) == relations_output()
    # 详细用例产物保持独立，不被图谱覆盖。
    detailed_attempt = attempts[detailed.current_artifact_attempt_id]
    assert detailed_attempt.worker_task_id == first.task_id


@pytest.mark.asyncio
async def test_relation_failure_allows_redispatch_with_prior_relations(db):
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_generate_task import AiGenerateTaskService

    run, first = create_run(db)
    event(
        db,
        run,
        first,
        status="success",
        stage="completed",
        output=cases_output(),
        config={"requirementAnalysis": {"functionalOverview": {}}},
    )
    approve(db, run)
    service = AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    await service.generate_relation_analysis("run", None, "u")
    graph_worker = db.scalar(
        select(WorkerTask)
        .where(WorkerTask.run_id == "run")
        .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
    )
    event(db, run, graph_worker, status="failed", stage="relation_analysis")
    assert run.status == "failed"
    assert run.current_stage == "relation_analysis"

    # 失败后允许再次点击；上一次关系产物随派发快照传入以保持编号稳定。
    redispatched = await service.generate_relation_analysis("run", None, "u")
    assert redispatched["status"] == "pending"
    assert redispatched["currentStage"] == "relation_analysis"
    retry_worker = db.scalar(
        select(WorkerTask)
        .where(WorkerTask.run_id == "run")
        .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
    )
    assert retry_worker.task_id != graph_worker.task_id
    stages, attempts = graph(db, run)
    relation = next(s for s in stages if s.stage == "relation_analysis")
    retry_attempt = attempts[relation.active_attempt_id]
    assert retry_attempt.worker_task_id == retry_worker.task_id
    config = retry_attempt.input_snapshot_json["config"]
    assert json.loads(config["resultYaml"])["cases"][0]["case_id"] == "case-1"
