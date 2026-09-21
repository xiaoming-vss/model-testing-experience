from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from authorization_database import AuthorizationDatabase

from testing_agent.core.errors import ErrBadRequest
from testing_agent.services import ai_generate_task as ai_tasks


@pytest.mark.asyncio
async def test_function_case_stage_output_persists_config_json():
    run = SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="waiting_review",
        checkpoint_enabled=True,
        current_stage="case_names",
        stage_status="waiting_review",
        snapshot_json={},
        error_message="",
        config_json={
            "enhancedText": "需求",
            "caseNames": {"categories": [{"model": "old", "data": []}]},
        },
        result_yaml="old",
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        async def get_run(self, run_id):
            assert run_id == "run-1"
            return run

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="functional_case_generate",
                project_id="project-1",
                creator_user_id="user-1",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    service = ai_tasks.AiGenerateTaskService(FakeRepository())

    payload = await service.save_stage_output(
        "run-1",
        {
            "stage": "case_names",
            "configJson": '{"categories":[{"model":"login","data":[]}]}',
        },
        "user-1",
    )

    assert payload["configJson"] == {
        "enhancedText": "需求",
        "caseNames": {"categories": [{"model": "login", "data": []}]},
    }
    assert run.config_json == {
        "enhancedText": "需求",
        "caseNames": {"categories": [{"model": "login", "data": []}]},
    }


def test_function_case_confirmed_import_matches_go_cases_payload():
    from test_function_confirmed_import import FunctionImportRepository, import_client

    repository = FunctionImportRepository()
    suite = repository.suites["suite-login"]
    suite.name = "登录"
    existing = repository.cases["case-existing"]
    existing.module = "登录"
    existing.title = "成功登录"
    repository.run.result_yaml = """{
  "cases": [
    {
      "case_id": "C001",
      "case_module": "登录",
      "case_title": "成功登录",
      "precondition": [
        "已创建账号"
      ],
      "test_steps": [
        "打开登录页",
        "输入账号"
      ],
      "expected_results": [
        "进入首页"
      ],
      "priority": "P1",
      "case_type": "功能"
    },
    {
      "case_id": "C002",
      "case_module": "支付",
      "case_title": "支付成功",
      "precondition": [
        "已登录"
      ],
      "test_steps": [
        "提交订单"
      ],
      "expected_results": [
        "支付成功"
      ],
      "priority": "P2",
      "case_type": "集成"
    }
  ]
}"""

    response = import_client(repository).post(
        "/v1/function-case-generate-task-runs/run-1/import",
        json={"confirmOverwrite": True},
    )

    assert response.status_code == 200
    assert existing.case_id == "case-existing"
    assert existing.preconditions == "已创建账号"
    assert existing.steps == "打开登录页\n输入账号"
    assert existing.expected_results == "进入首页"
    assert existing.priority == "P1"
    assert existing.case_type == "功能"
    created = repository.cases["C002"]
    assert created.suite_id == repository.suites_by_name["支付"].suite_id
    assert created.title == "支付成功"
    assert created.preconditions == "已登录"
    assert created.steps == "提交订单"
    assert created.expected_results == "支付成功"
    assert created.priority == "P2"
    assert created.case_type == "集成"
    assert created.order_no == 1
    assert repository.run.import_status == "imported"


def test_function_case_import_replaces_an_identifier_already_in_use():
    from test_function_confirmed_import import FunctionImportRepository, import_client

    repository = FunctionImportRepository()
    taken = repository.cases.pop("case-existing")
    taken.case_id = "C002"
    repository.cases["C002"] = taken
    repository.run.result_yaml = """{
  "cases": [
    {
      "case_id": "C002",
      "case_module": "支付",
      "case_title": "支付成功",
      "precondition": [
        "已登录"
      ],
      "test_steps": [
        "提交订单"
      ],
      "expected_results": [
        "支付成功"
      ],
      "priority": "P2",
      "case_type": "集成"
    }
  ]
}"""

    response = import_client(repository).post(
        "/v1/function-case-generate-task-runs/run-1/import", json={}
    )

    assert response.status_code == 200
    created = [case for case in repository.cases.values() if case is not taken]
    assert len(created) == 1
    assert created[0].case_id != "C002"
    assert UUID(created[0].case_id).version == 4
    assert taken.case_id == "C002"


def test_generated_function_case_keeps_upstream_case_id():
    def generated(case_id=None):
        return {
            **({"case_id": case_id} if case_id is not None else {}),
            "case_module": "登录",
            "case_title": "成功登录",
            "precondition": ["1. 已创建账号"],
            "test_steps": ["1. 打开登录页"],
            "expected_results": ["1. 进入首页"],
            "priority": "2",
            "case_type": "功能测试",
        }

    assert ai_tasks.validate_function_candidate_cases([generated("C001")])[0]["case_id"] == "C001"
    assert ai_tasks.validate_function_candidate_cases([generated()])[0]["case_id"] == ""
    with pytest.raises(type(ErrBadRequest)):
        ai_tasks.validate_function_candidate_cases([generated("C" * 65)])
