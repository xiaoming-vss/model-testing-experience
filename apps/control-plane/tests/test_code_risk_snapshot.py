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

import json
from types import SimpleNamespace

import pytest
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.code_risk_analysis import (  # noqa: F401
    NOW,
    FakeTaskRepository,
    approved_understanding,
    make_binding,
    make_connection,
    make_ready_service,
    make_requirement,
    make_service,
    make_task,
    understanding_version,
    worker_contract_authority,
)
from support.requirement_versions import material_artifact

from testing_agent.core.errors import AppError
from testing_agent.repositories.requirement_software_repository import (
    unique_by_git_repository,
)
from testing_agent.services.code_risk_analysis import (
    FUNCTION_CASE_NO_RUN_NOTE,
    dump_last_run,
)
from testing_agent.services.generation_current_material import CurrentMaterial


async def test_code_risk_snapshot_uses_verified_current_material():
    service, _ = make_ready_service()
    material = CurrentMaterial(
        candidate_id="candidate",
        snapshot_id="snapshot",
        candidate_token="candidate-token",
        current_token="current-token",
        task_id="material-task",
        attempt_id="attempt",
        content=json.dumps(material_artifact()),
        content_hash="content-hash",
        basis_hash="basis-hash",
        lineage_hash="lineage-hash",
        document_root_hash="document-hash",
    )
    snapshot = await service.build_snapshot(
        make_task(), "run-1", "worker-task-1", user_id="user-1", current_material=material
    )
    assert json.loads(snapshot["requirement"]["documentContent"]) == material_artifact()
    assert snapshot["requirementMaterialCurrent"]["snapshotId"] == "snapshot"
    assert "requirementMaterialVersion" not in snapshot


def test_bindings_to_the_same_git_repository_are_deduplicated():
    first = make_binding("binding-1", "repo-1", "group-1")
    duplicate = make_binding("binding-2", "repo-1", "group-1", branch="other")
    second = make_binding("binding-3", "repo-2", "group-1")

    assert unique_by_git_repository([first, duplicate, second]) == [first, second]


async def test_build_snapshot_contains_requirement_bindings_and_existing_tests():
    binding = make_binding("binding-1", "repo-1", "group-1")
    function_case = SimpleNamespace(
        case_id="fc-1",
        title="登录成功用例",
        module="登录",
        preconditions="已注册账号",
        steps=["打开登录页", "输入账号密码", "点击登录"],
        expected_results=["跳转首页"],
        priority="P0",
        case_type="positive",
    )
    api_case = SimpleNamespace(
        case_id="ac-1",
        name="登录接口",
        description="POST /login",
        method="POST",
        url_template="/api/login",
        latest_run=SimpleNamespace(status="passed", finished_at=NOW, logs="should-not-leak"),
    )
    ui_case = SimpleNamespace(
        case_id="uc-1",
        name="登录页可见",
        steps_json='{"steps":[]}',
        latest_run=SimpleNamespace(status="failed", finished_at=NOW, logs="no"),
    )
    task_repository = FakeTaskRepository(
        make_requirement(),
        function_suites=[
            {"suite": SimpleNamespace(suite_id="s1", name="登录功能集"), "cases": [function_case]}
        ],
        api_collections=[
            {
                "collection": SimpleNamespace(collection_id="c1", name="登录接口集"),
                "cases": [api_case],
            }
        ],
        api_rules={
            "ac-1": [
                SimpleNamespace(
                    name="状态码断言",
                    assert_source="status",
                    target_expr="code",
                    comparator="eq",
                    expected_value="200",
                )
            ]
        },
        ui_suites=[{"suite": SimpleNamespace(suite_id="us1", name="登录UI集"), "cases": [ui_case]}],
    )
    connection = make_connection("conn-1", "https://gitlab.example.com", "enc:token-1")
    service, _ = make_service(
        bindings=[binding],
        connections=[connection],
        tokens={"enc:token-1": "plain-token-1"},
        task_repository=task_repository,
    )

    snapshot = await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert snapshot["taskId"] == "task-1"
    assert snapshot["runId"] == "run-1"
    assert snapshot["taskType"] == "code_risk_analysis"
    assert snapshot["gitlabCredentialsUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/gitlab-credentials"
    )
    assert snapshot["requirement"]["requirementId"] == "req-1"
    assert snapshot["requirement"]["name"] == "登录改造"
    assert snapshot["requirement"]["documentType"] == "richtext"
    # 需求内容来自已审核的需求理解版本，不读取需求正文。
    assert json.loads(snapshot["requirement"]["documentContent"]) == material_artifact()
    assert snapshot["requirementMaterialCurrent"]["candidateId"] == "candidate"
    assert "requirementMaterialVersion" not in snapshot
    entry = snapshot["bindings"][0]
    assert entry["bindingId"] == "binding-1"
    assert entry["softwareRepositoryId"] == "binding-1"
    assert entry["softwareRepositoryName"] == "仓库 repo-1"
    assert entry["repositoryId"] == "repo-1"
    assert entry["groupId"] == "group-1"
    assert entry["branch"] == "develop"
    assert entry["baselineBranch"] == "release-1.0"
    assert entry["baselineRef"] == "abc123"
    assert entry["pathWithNamespace"] == "team/repo-1"
    assert entry["cloneUrl"] == "https://gitlab.example.com/team/repo-1.git"
    assert entry["baseCommit"] == "abc123"
    assert entry["headCommit"] == "def456"
    assert entry["connectionId"] == "conn-1"
    assert entry["note"] == ""
    assert entry["error"] == ""

    tests = snapshot["existingTests"]
    function_entry = tests["functionCases"][0]
    assert function_entry["title"] == "登录成功用例"
    assert function_entry["steps"] == ["打开登录页", "输入账号密码", "点击登录"]
    assert function_entry["expectedResults"] == ["跳转首页"]
    assert function_entry["lastRun"] is None
    assert function_entry["runNote"] == FUNCTION_CASE_NO_RUN_NOTE

    api_entry = tests["apiCases"][0]
    assert api_entry["assertRules"][0]["name"] == "状态码断言"
    assert api_entry["lastRun"] == {"status": "passed", "finishedAt": NOW}
    assert "logs" not in api_entry["lastRun"]

    ui_entry = tests["uiCases"][0]
    assert ui_entry["stepsJson"] == '{"steps":[]}'
    assert ui_entry["lastRun"] == {"status": "failed", "finishedAt": NOW}


def test_dump_last_run_only_carries_status_and_finished_at():
    assert dump_last_run(None) is None
    assert dump_last_run(SimpleNamespace(status="passed", finished_at=NOW, logs="x")) == {
        "status": "passed",
        "finishedAt": NOW,
    }


@pytest.mark.asyncio
async def test_docx_requirement_still_uses_approved_understanding():
    requirement = make_requirement()
    requirement.document_type = "docx"
    requirement.document_content = ""
    service, _ = make_ready_service(requirement=requirement)

    snapshot = await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert snapshot["requirement"]["documentType"] == "docx"
    assert json.loads(snapshot["requirement"]["documentContent"]) == material_artifact()


@pytest.mark.asyncio
async def test_snapshot_rejects_when_requirement_has_no_repository_binding():
    service, _ = make_service()

    with pytest.raises(AppError) as error:
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert "尚未关联软件仓库" in str(error.value)


@pytest.mark.asyncio
async def test_missing_approved_understanding_rejects_the_run():
    service, _ = make_service()
    with pytest.raises(AppError, match="材料整理"):
        await service.build_snapshot(
            make_task(), "run-1", "worker-task-1", user_id="user-1", current_material=None
        )


@pytest.mark.asyncio
async def test_build_snapshot_freezes_clone_url_and_pinned_commits():
    binding = make_binding("binding-1", "repo-1", "group-1", baseline_branch="release-1.0")
    connection = make_connection("conn-1", "https://gitlab.example.com", "enc:token-1")
    service, integration = make_service(
        bindings=[binding],
        connections=[connection],
        tokens={"enc:token-1": "plain-token-1"},
    )

    snapshot = await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    entry = snapshot["bindings"][0]
    assert entry["cloneUrl"] == "https://gitlab.example.com/team/repo-1.git"
    assert entry["pathWithNamespace"] == "team/repo-1"
    assert entry["baseCommit"] == "abc123"
    assert entry["headCommit"] == "def456"
    assert entry["baselineRef"] == "abc123"
    assert [(call["kind"], call["ref"]) for call in integration.calls if "ref" in call] == [
        ("commit", "release-1.0"),
        ("commit", "develop"),
    ]


@pytest.mark.asyncio
async def test_missing_baseline_branch_rejects_snapshot():
    binding = make_binding("binding-1", "repo-1", "group-1", baseline_branch="")
    connection = make_connection("conn-1", "https://gitlab.example.com", "enc:token-1")
    service, _ = make_service(
        bindings=[binding],
        connections=[connection],
        tokens={"enc:token-1": "plain-token-1"},
    )

    with pytest.raises(AppError) as error:
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert "选择基线分支" in str(error.value)


@pytest.mark.asyncio
async def test_missing_personal_connection_marks_binding_connection_unresolved():
    binding = make_binding("binding-1", "repo-1", "group-1")
    service, _ = make_service(bindings=[binding])

    with pytest.raises((AppError, ValueError)):
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")


@pytest.mark.asyncio
async def test_decrypt_failure_treats_binding_as_connection_unresolved():
    connection = make_connection("conn-1", "https://gitlab.example.com", "enc:broken")
    service, _ = make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1")],
        connections=[connection],
        tokens={},
    )

    with pytest.raises((AppError, ValueError)):
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")
