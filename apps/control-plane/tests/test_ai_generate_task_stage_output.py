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


@pytest.mark.asyncio
async def test_function_case_review_import_matches_go_cases_payload():
    existing_suite = SimpleNamespace(suite_id="suite-login", name="登录")
    existing_case = SimpleNamespace(
        case_id="case-login",
        suite_id="suite-login",
        module="登录",
        title="成功登录",
        preconditions="old",
        steps="old",
        expected_results="old",
        priority="P3",
        case_type="功能",
        order_no=1,
    )

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.added = []
            self.suites = {"登录": existing_suite}
            self.cases = {("suite-login", "成功登录"): existing_case}
            self.by_id = {existing_case.case_id: existing_case}

        async def get_case(self, case_id):
            return self.by_id.get(case_id)

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(requirement_id="requirement-1", sprint_id="sprint-1")

        async def get_sprint(self, sprint_id):
            assert sprint_id == "sprint-1"
            return SimpleNamespace(sprint_id="sprint-1", project_id="project-1")

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_function_suite_by_requirement_and_name(self, requirement_id, name):
            assert requirement_id == "requirement-1"
            return self.suites.get(name)

        async def get_function_case_by_suite_and_title(self, suite_id, title):
            return self.cases.get((suite_id, title))

        async def max_function_case_order_by_suite(self, suite_id):
            return 1 if suite_id == "suite-login" else 0

        def add(self, row):
            self.added.append(row)
            if hasattr(row, "suite_id") and hasattr(row, "name"):
                self.suites[row.name] = row
            if getattr(row, "case_id", None):
                self.by_id[row.case_id] = row

    run = SimpleNamespace(
        requirement_id="requirement-1",
        result_yaml=(
            '{"cases":['
            '{"case_id":"C001","case_module":"登录","case_title":"成功登录",'
            '"precondition":["已创建账号"],'
            '"test_steps":["打开登录页","输入账号"],"expected_results":["进入首页"],'
            '"priority":"P1","case_type":"功能"},'
            '{"case_id":"C002","case_module":"支付","case_title":"支付成功",'
            '"precondition":["已登录"],'
            '"test_steps":["提交订单"],"expected_results":["支付成功"],'
            '"priority":"P2","case_type":"集成"}'
            "]}"
        ),
    )
    repository = FakeRepository()
    service = ai_tasks.AiGenerateTaskService(repository)

    suite_ids = await service.import_generated_function_cases("user-1", run)

    assert suite_ids == ["suite-login", repository.suites["支付"].suite_id]
    assert existing_case.module == "登录"
    assert existing_case.preconditions == "已创建账号"
    assert existing_case.steps == "打开登录页\n输入账号"
    assert existing_case.expected_results == "进入首页"
    assert existing_case.priority == "P1"
    assert existing_case.case_type == "功能"

    created_suites = [
        row for row in repository.added if hasattr(row, "suite_id") and hasattr(row, "name")
    ]
    created_cases = [row for row in repository.added if hasattr(row, "case_id")]
    assert [suite.name for suite in created_suites] == ["支付"]
    assert len(created_cases) == 1
    assert created_cases[0].suite_id == repository.suites["支付"].suite_id
    assert created_cases[0].module == "支付"
    assert created_cases[0].title == "支付成功"
    assert created_cases[0].preconditions == "已登录"
    assert created_cases[0].steps == "提交订单"
    assert created_cases[0].expected_results == "支付成功"
    assert created_cases[0].priority == "P2"
    assert created_cases[0].case_type == "集成"
    assert created_cases[0].order_no == 1
    # 候选编号在首次入库时固定成用例 ID，已入库的用例保持原 ID 不变。
    assert created_cases[0].case_id == "C002"
    assert existing_case.case_id == "case-login"


@pytest.mark.asyncio
async def test_function_case_import_replaces_an_identifier_already_in_use():
    taken = SimpleNamespace(case_id="C002", suite_id="suite-other", title="历史用例")

    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.added = []
            self.by_id = {taken.case_id: taken}

        async def get_case(self, case_id):
            return self.by_id.get(case_id)

        async def get_requirement(self, requirement_id):
            return SimpleNamespace(requirement_id="requirement-1", sprint_id="sprint-1")

        async def get_sprint(self, sprint_id):
            return SimpleNamespace(sprint_id="sprint-1", project_id="project-1")

        async def get_project(self, project_id):
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def get_function_suite_by_requirement_and_name(self, requirement_id, name):
            return None

        async def get_function_case_by_suite_and_title(self, suite_id, title):
            return None

        async def max_function_case_order_by_suite(self, suite_id):
            return 0

        def add(self, row):
            self.added.append(row)

    run = SimpleNamespace(
        requirement_id="requirement-1",
        result_yaml=(
            '{"cases":[{"case_id":"C002","case_module":"支付","case_title":"支付成功",'
            '"precondition":["已登录"],"test_steps":["提交订单"],'
            '"expected_results":["支付成功"],"priority":"P2","case_type":"集成"}]}'
        ),
    )
    repository = FakeRepository()

    await ai_tasks.AiGenerateTaskService(repository).import_generated_function_cases("user-1", run)

    created = [row for row in repository.added if hasattr(row, "case_id")]
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
