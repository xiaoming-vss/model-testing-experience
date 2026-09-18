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

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from testing_agent.api.deps import (
    get_ai_generate_task_service,
    get_current_user_id,
    get_worker_task_service,
)
from testing_agent.app import create_app
from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import WorkerTaskEventRequest
from testing_agent.services import worker_task as worker_task_service_module
from testing_agent.services.ai_generate_task import AiGenerateTaskService, dump_run
from testing_agent.services.code_risk_analysis import (
    FUNCTION_CASE_NO_RUN_NOTE,
    CodeRiskAnalysisService,
    dump_code_risk_analysis_run,
    dump_last_run,
    gitlab_credentials_payload,
    parse_risk_report,
)
from testing_agent.services.worker import apply_ai_completion_to_run
from testing_agent.services.worker_task import WorkerTaskService

NOW = datetime(2026, 8, 20, 10, 30, tzinfo=UTC)

RISK_REPORT_YAML = """\
analyzedAt: "2026-08-21T10:30:00Z"
repositories:
  - repositoryId: "repo-1"
    branch: "develop"
    baselineCommit: "abc123"
    headCommit: "def456"
changeOverview:
  filesChanged: 12
  additions: 340
  deletions: 120
risks:
  - level: "high"
    location: "src/auth.py"
    reason: "鉴权逻辑变更"
affectedCases:
  - caseType: "api"
    caseId: "ac-1"
    title: "登录接口"
    impact: "参数校验变更"
coverageGaps:
  - gap: "登录失败路径无用例覆盖"
    suggestion: "新增失败路径用例"
"""


def make_task(**overrides) -> SimpleNamespace:
    fields = {
        "task_id": "task-1",
        "task_type": "code_risk_analysis",
        "name": "登录改造 代码风险分析",
        "project_id": "project-1",
        "sprint_id": "sprint-1",
        "requirement_id": "req-1",
        "source_type": "text",
        "instruction": "",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def make_requirement() -> SimpleNamespace:
    return SimpleNamespace(
        requirement_id="req-1",
        name="登录改造",
        document_type="text",
        document_content="登录模块需求正文",
        document_storage_path="",
        document_filename="",
        document_download_url="",
    )


def make_binding(
    binding_id: str,
    repository_id: str,
    group_id: str,
    branch: str = "develop",
    baseline_branch: str = "release-1.0",
) -> SimpleNamespace:
    return SimpleNamespace(
        binding_id=binding_id,
        instance_url="https://gitlab.example.com",
        instance_key="gitlab-example",
        remote_resource_id=repository_id,
        remote_parent_id=group_id,
        extra_json={"branch": branch, "baseline_branch": baseline_branch},
    )


def make_connection(connection_id: str, base_url: str, encrypted_token: str) -> SimpleNamespace:
    return SimpleNamespace(
        connection_id=connection_id,
        provider="gitlab",
        project_id="project-1",
        base_url=base_url,
        access_token=encrypted_token,
    )


class FakeCipher:
    def __init__(self, tokens: dict[str, str]):
        self.tokens = tokens

    def decrypt(self, value: str) -> str:
        if value not in self.tokens:
            raise ValueError("bad ciphertext")
        return self.tokens[value]


class FakeTaskRepository:
    def __init__(
        self,
        requirement: SimpleNamespace,
        function_suites: list | None = None,
        api_collections: list | None = None,
        ui_suites: list | None = None,
        api_rules: dict[str, list] | None = None,
    ):
        self.requirement = requirement
        self.function_suites = function_suites or []
        self.api_collections = api_collections or []
        self.ui_suites = ui_suites or []
        self.api_rules = api_rules or {}

    async def get_requirement(self, requirement_id: str):
        return self.requirement

    async def list_function_suites_by_requirement(self, requirement_id: str):
        return [suite["suite"] for suite in self.function_suites]

    async def list_function_cases(self, suite_id: str):
        return [
            suite["cases"] for suite in self.function_suites if suite["suite"].suite_id == suite_id
        ][0]

    async def list_api_collections_by_requirement(self, requirement_id: str):
        return [row["collection"] for row in self.api_collections]

    async def list_api_cases(self, collection_id: str):
        return [
            row["cases"]
            for row in self.api_collections
            if row["collection"].collection_id == collection_id
        ][0]

    async def list_api_assert_rules(self, case_id: str):
        return self.api_rules.get(case_id, [])

    async def get_latest_api_case_run(self, case_id: str):
        for row in self.api_collections:
            for case in row["cases"]:
                if case.case_id == case_id:
                    return case.latest_run
        return None

    async def list_ui_suites_by_requirement(self, requirement_id: str):
        return [suite["suite"] for suite in self.ui_suites]

    async def list_ui_cases(self, suite_id: str):
        return [suite["cases"] for suite in self.ui_suites if suite["suite"].suite_id == suite_id][
            0
        ]

    async def get_latest_ui_case_run(self, case_id: str):
        for suite in self.ui_suites:
            for case in suite["cases"]:
                if case.case_id == case_id:
                    return case.latest_run
        return None


class FakeBindingRepository:
    def __init__(self, bindings: list, group_bindings: dict[str, SimpleNamespace] | None = None):
        self.bindings = bindings
        self.group_bindings = group_bindings or {}

    async def list_active_repo_bindings_for_requirement(self, requirement_id: str):
        return self.bindings

    async def get_active_project_group_binding(self, provider, project_id, group_id, instance=""):
        return self.group_bindings.get(group_id)


class FakeBaselineResolutionService:
    def __init__(self, resolutions: list):
        self.resolutions = resolutions
        self.captured_branch_exists = None

    async def resolve_requirement_bindings(self, requirement_id):
        from testing_agent.services.baseline_resolution import (
            BindingResolution,
            RepoBaselineResolution,
        )

        return [
            BindingResolution(
                binding,
                self.resolutions[i]
                if i < len(self.resolutions)
                else RepoBaselineResolution(binding.remote_resource_id, "develop", "release-1.0"),
            )
            for i, binding in enumerate(self.bindings)
        ]


class FakeIntegrationConnectionService:
    def __init__(self, connections: list, branches: list | None = None):
        self.connections = {c.connection_id: c for c in connections}
        self.calls: list[dict] = []
        self.gitlab_resource_client = SimpleNamespace(
            list_repository_branches=self._list_repository_branches
        )
        self.branches = branches

    async def resolve_personal_connection(
        self, user_id, provider, project_id, instance_url, connection_id=""
    ):
        assert user_id == "user-1"
        return next(c for c in self.connections.values() if c.base_url == instance_url)

    async def _list_repository_branches(
        self, base_url, access_token, repository_id, *, search="", page=1, page_size=100
    ):
        self.calls.append(
            {
                "base_url": base_url,
                "access_token": access_token,
                "repository_id": repository_id,
                "search": search,
            }
        )
        return {"items": self.branches if self.branches is not None else [{"name": search}]}


def make_service(
    *,
    bindings: list | None = None,
    group_bindings: dict | None = None,
    resolutions: list | None = None,
    connections: list | None = None,
    branches: list | None = None,
    tokens: dict | None = None,
    requirement: SimpleNamespace | None = None,
    task_repository: FakeTaskRepository | None = None,
) -> tuple[CodeRiskAnalysisService, FakeBaselineResolutionService]:
    bindings = bindings if bindings is not None else []
    resolutions = resolutions or []
    service = CodeRiskAnalysisService(
        task_repository or FakeTaskRepository(requirement or make_requirement()),
        FakeBindingRepository(bindings, group_bindings or {}),
        FakeBaselineResolutionService(resolutions),
        FakeIntegrationConnectionService(connections or [], branches),
        FakeCipher(tokens or {}),
    )
    service.baseline_resolution_service.bindings = bindings
    return service, service.baseline_resolution_service  # type: ignore[attr-defined]


def make_run(**overrides) -> SimpleNamespace:
    fields = {
        "run_id": "run-1",
        "task_id": "task-1",
        "requirement_id": "req-1",
        "sprint_id": "sprint-1",
        "project_id": "project-1",
        "trigger_user_id": "user-1",
        "trigger_type": "manual",
        "status": "failed",
        "checkpoint_enabled": False,
        "current_stage": "",
        "stage_status": "",
        "snapshot_json": {},
        "error_message": "GitLab 基线分支已删除",
        "remediation": "请在仓库设置中恢复基线分支或重新绑定",
        "config_json": {},
        "result_yaml": "",
        "result_summary_json": {},
        "review_status": "pending",
        "reviewer_user_id": "",
        "reviewed_at": None,
        "review_comment": "",
        "duration_ms": 0,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class FakeSession:
    def __init__(self, responses: list):
        self.responses = list(responses)

    async def scalar(self, stmt):
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# 快照组装
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_snapshot_contains_requirement_bindings_and_existing_tests():
    binding = make_binding("binding-1", "repo-1", "group-1")
    resolution = SimpleNamespace(repository_id="repo-1", baseline_ref="abc123", note="", error="")
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
        group_bindings={"group-1": SimpleNamespace(connection_id="conn-1")},
        resolutions=[resolution],
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
    assert snapshot["requirement"] == {
        "requirementId": "req-1",
        "name": "登录改造",
        "documentType": "text",
        "documentContent": "登录模块需求正文",
    }
    entry = snapshot["bindings"][0]
    assert entry["bindingId"] == "binding-1"
    assert entry["repositoryId"] == "repo-1"
    assert entry["groupId"] == "group-1"
    assert entry["branch"] == "develop"
    assert entry["baselineBranch"] == "release-1.0"
    assert entry["baselineRef"] == "abc123"
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
async def test_docx_without_content_falls_back_to_internal_document_url():
    requirement = make_requirement()
    requirement.document_type = "docx"
    requirement.document_content = ""
    service, _ = make_service(requirement=requirement)

    snapshot = await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert snapshot["requirement"]["documentType"] == "docx"
    assert snapshot["requirement"]["documentContent"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )


@pytest.mark.asyncio
async def test_branch_checker_is_wired_to_resolve_via_snapshot_connection():
    binding = make_binding("binding-1", "repo-1", "group-1", baseline_branch="release-1.0")
    connection = make_connection("conn-1", "https://gitlab.example.com", "enc:token-1")
    service, baseline = make_service(
        bindings=[binding],
        group_bindings={"group-1": SimpleNamespace(connection_id="conn-1")},
        resolutions=[],
        connections=[connection],
        tokens={"enc:token-1": "plain-token-1"},
        branches=[{"name": "main"}, {"name": "develop"}],
    )

    await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    call = service.integration_connection_service.calls[0]  # type: ignore[attr-defined]
    assert call["base_url"] == "https://gitlab.example.com"
    assert call["access_token"] == "plain-token-1"
    assert call["repository_id"] == "repo-1"
    assert call["search"] == "release-1.0"


@pytest.mark.asyncio
async def test_branch_checker_raises_when_repo_has_no_resolved_connection():
    service, baseline = make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1")],
        resolutions=[],
    )

    with pytest.raises((AppError, ValueError)):
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")


@pytest.mark.asyncio
async def test_missing_group_binding_marks_binding_connection_unresolved():
    binding = make_binding("binding-1", "repo-1", "group-missing")
    resolution = SimpleNamespace(
        repository_id="repo-1", baseline_ref=None, note="基线分支缺失", error=""
    )
    service, _ = make_service(bindings=[binding], resolutions=[resolution])

    with pytest.raises((AppError, ValueError)):
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")


@pytest.mark.asyncio
async def test_decrypt_failure_treats_binding_as_connection_unresolved():
    connection = make_connection("conn-1", "https://gitlab.example.com", "enc:broken")
    service, _ = make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1")],
        group_bindings={"group-1": SimpleNamespace(connection_id="conn-1")},
        resolutions=[],
        connections=[connection],
        tokens={},
    )

    with pytest.raises((AppError, ValueError)):
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")


# ---------------------------------------------------------------------------
# GitLab 凭据负载
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitlab_credentials_payload_groups_by_connection_and_decrypts():
    session = FakeSession(
        [
            make_connection("conn-1", "https://gitlab.example.com", "enc:1"),
            make_connection("conn-2", "https://gitlab.example.com", "enc:2"),
        ]
    )
    bindings = [
        {"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"},
        {"bindingId": "b2", "repositoryId": "repo-2", "connectionId": "conn-1"},
        {"bindingId": "b3", "repositoryId": "repo-3", "connectionId": "conn-2"},
        {"bindingId": "b4", "repositoryId": "repo-4", "connectionId": ""},
    ]

    payload = await gitlab_credentials_payload(
        session,
        "worker-task-1",
        "project-1",
        bindings,
        FakeCipher({"enc:1": "t1", "enc:2": "t2"}),
        user_id="user-1",
    )

    assert payload["taskId"] == "worker-task-1"
    assert payload["bindings"] == bindings
    credentials = payload["credentials"]
    assert [c["connectionId"] for c in credentials] == ["conn-1", "conn-2"]
    assert credentials[0]["baseUrl"] == "https://gitlab.example.com"
    assert credentials[0]["accessToken"] == "t1"
    assert credentials[0]["repositoryIds"] == ["repo-1", "repo-2"]
    assert credentials[1]["repositoryIds"] == ["repo-3"]


@pytest.mark.asyncio
async def test_gitlab_credentials_payload_raises_when_connection_missing():
    with pytest.raises(AppError) as excinfo:
        await gitlab_credentials_payload(
            FakeSession([None]),
            "worker-task-1",
            "project-1",
            [{"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"}],
            FakeCipher({}),
            user_id="user-1",
        )
    assert excinfo.value.code == 3401


@pytest.mark.asyncio
async def test_gitlab_credentials_payload_raises_when_cipher_missing():
    with pytest.raises(AppError) as excinfo:
        await gitlab_credentials_payload(
            FakeSession([make_connection("conn-1", "https://gitlab.example.com", "enc:1")]),
            "worker-task-1",
            "project-1",
            [{"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"}],
            None,
            user_id="user-1",
        )
    assert excinfo.value.code == 3403
    assert "解密密钥未配置" in excinfo.value.message


@pytest.mark.asyncio
async def test_gitlab_credentials_payload_raises_on_decrypt_failure():
    with pytest.raises(AppError) as excinfo:
        await gitlab_credentials_payload(
            FakeSession([make_connection("conn-1", "https://gitlab.example.com", "enc:bad")]),
            "worker-task-1",
            "project-1",
            [{"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"}],
            FakeCipher({}),
            user_id="user-1",
        )
    assert excinfo.value.code == 3403
    assert "解密失败" in excinfo.value.message


# ---------------------------------------------------------------------------
# WorkerTaskService.gitlab_credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_task_service_gitlab_credentials_rejects_other_task_types(monkeypatch):
    async def fake_find_task(session, domain, task_id):
        return SimpleNamespace(task_id=task_id, task_type="api_case_generate", run_id="run-1")

    monkeypatch.setattr(worker_task_service_module, "find_task", fake_find_task)

    with pytest.raises(AppError) as excinfo:
        await WorkerTaskService(SimpleNamespace(session=object())).gitlab_credentials("task-1")
    assert excinfo.value.code == 404


@pytest.mark.asyncio
async def test_worker_task_service_gitlab_credentials_reads_run_snapshot(monkeypatch):
    class FakeRepository:
        session = object()

        async def get_ai_run(self, run_id):
            assert run_id == "run-1"
            return SimpleNamespace(
                run_id="run-1",
                project_id="project-1",
                snapshot_json={
                    "bindings": [
                        {"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"}
                    ]
                },
            )

    async def fake_find_task(session, domain, task_id):
        return SimpleNamespace(task_id=task_id, task_type="code_risk_analysis", run_id="run-1")

    async def fake_payload(session, task_id, project_id, bindings, cipher, *, user_id):
        assert task_id == "worker-task-1"
        assert project_id == "project-1"
        assert bindings[0]["repositoryId"] == "repo-1"
        return {"taskId": task_id, "credentials": []}

    monkeypatch.setattr(worker_task_service_module, "find_task", fake_find_task)
    monkeypatch.setattr(worker_task_service_module, "gitlab_credentials_payload", fake_payload)

    payload = await WorkerTaskService(FakeRepository()).gitlab_credentials("worker-task-1")
    assert payload["taskId"] == "worker-task-1"


@pytest.mark.asyncio
async def test_worker_requirement_document_allows_code_risk_analysis():
    class FakeRepository:
        session = object()

        async def get_worker_task(self, domain, task_id):
            assert domain == "ai"
            return SimpleNamespace(
                task_id=task_id,
                task_type="code_risk_analysis",
                run_id="run-1",
                generate_task_id="task-1",
            )

        async def get_ai_run(self, run_id):
            return SimpleNamespace(run_id="run-1", requirement_id="req-1", task_id="task-1")

        async def get_requirement(self, requirement_id):
            return SimpleNamespace(
                requirement_id="req-1",
                document_storage_path="",
                document_content="需求正文",
                document_filename="",
            )

    requirement = await WorkerTaskService(FakeRepository()).requirement_document("worker-task-1")
    assert requirement.document_content == "需求正文"


# ---------------------------------------------------------------------------
# 失败错误消息与补救建议回显
# ---------------------------------------------------------------------------


def test_apply_ai_completion_to_run_records_remediation_and_error():
    run = make_run()
    body = WorkerTaskEventRequest(
        workerId="worker-1",
        taskId="task-1",
        runId="run-1",
        status="failed",
        errorMessage="GitLab 基线分支已删除",
        remediation="请在仓库设置中恢复基线分支",
    )

    apply_ai_completion_to_run(run, body)

    payload = dump_run(run)
    assert payload["status"] == "failed"
    assert payload["errorMessage"] == "GitLab 基线分支已删除"
    assert payload["remediation"] == "请在仓库设置中恢复基线分支"


def test_apply_ai_completion_to_run_remediation_falls_back_to_snapshot():
    run = make_run()
    body = WorkerTaskEventRequest(
        workerId="worker-1",
        status="failed",
        snapshotJson={"errorMessage": "快照错误", "remediation": "快照建议"},
    )

    apply_ai_completion_to_run(run, body)

    assert run.error_message == "快照错误"
    assert run.remediation == "快照建议"


def test_apply_ai_completion_to_run_remediation_defaults_to_empty():
    run = make_run()
    apply_ai_completion_to_run(run, WorkerTaskEventRequest(workerId="worker-1", status="success"))
    assert run.remediation == ""


# ---------------------------------------------------------------------------
# 风险报告解析与回读(工单 07,RC-5)
# ---------------------------------------------------------------------------


def test_parse_risk_report_full_structure():
    report = parse_risk_report(RISK_REPORT_YAML)

    assert report["analyzedAt"] == "2026-08-21T10:30:00Z"
    assert report["repositories"] == [
        {
            "repositoryId": "repo-1",
            "branch": "develop",
            "baselineCommit": "abc123",
            "headCommit": "def456",
        }
    ]
    assert report["changeOverview"] == {"filesChanged": 12, "additions": 340, "deletions": 120}
    assert report["risks"][0]["level"] == "high"
    assert report["affectedCases"][0]["caseId"] == "ac-1"
    assert report["coverageGaps"][0]["suggestion"] == "新增失败路径用例"


def test_parse_risk_report_accepts_snake_case_aliases():
    report = parse_risk_report(
        """\
analyzed_at: "2026-08-21T10:30:00Z"
repositories:
  - repository_id: "repo-2"
    branch: "main"
    baseline_commit: "111"
    head_commit: "222"
change_overview:
  filesChanged: 1
risk_list:
  - level: "low"
    reason: "小改动"
affected_cases:
  - caseId: "fc-1"
coverage_gaps:
  - gap: "缺口"
"""
    )

    assert report["analyzedAt"] == "2026-08-21T10:30:00Z"
    assert report["repositories"] == [
        {
            "repositoryId": "repo-2",
            "branch": "main",
            "baselineCommit": "111",
            "headCommit": "222",
        }
    ]
    assert report["changeOverview"] == {"filesChanged": 1}
    assert report["risks"] == [{"level": "low", "reason": "小改动"}]
    assert report["affectedCases"] == [{"caseId": "fc-1"}]
    assert report["coverageGaps"] == [{"gap": "缺口"}]


def test_parse_risk_report_repository_normalizes_keys_and_keeps_extra_fields():
    report = parse_risk_report(
        """\
repositories:
  - repository_id: "repo-3"
    baseline_commit: "aaa"
    head_commit: "bbb"
    note: "保留字段"
"""
    )

    assert report["repositories"] == [
        {"repositoryId": "repo-3", "baselineCommit": "aaa", "headCommit": "bbb", "note": "保留字段"}
    ]


def test_parse_risk_report_rejects_non_string_analyzed_at():
    # 契约要求 analyzedAt 为字符串;未加引号的时间戳被 YAML 解析为 datetime,
    # 属形态不符,整体返回 None 而非静默改写格式。
    assert parse_risk_report("analyzedAt: 2026-08-21T10:30:00Z\nrisks: []\n") is None


def test_parse_risk_report_rejects_wrong_shaped_section():
    assert parse_risk_report('risks: "not-a-list"\n') is None
    assert parse_risk_report("changeOverview:\n  - not-an-object\n") is None
    assert parse_risk_report("repositories:\n  - not-an-object\n") is None


def test_parse_risk_report_fills_missing_sections_with_none():
    report = parse_risk_report('risks:\n  - level: "high"\n')

    assert report["risks"] == [{"level": "high"}]
    assert report["analyzedAt"] is None
    assert report["repositories"] == []
    assert report["changeOverview"] is None
    assert report["affectedCases"] is None
    assert report["coverageGaps"] is None


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "cases: []", "- a\n- b", "not: [valid", "just a string"],
)
def test_parse_risk_report_returns_none_when_empty_or_unrecognized(raw):
    assert parse_risk_report(raw) is None


def test_dump_code_risk_analysis_run_includes_parsed_report():
    run = make_run(status="success", result_yaml=RISK_REPORT_YAML)

    payload = dump_code_risk_analysis_run(run)

    assert payload["resultYaml"] == RISK_REPORT_YAML
    report = payload["report"]
    assert report["analyzedAt"] == "2026-08-21T10:30:00Z"
    assert report["repositories"][0]["baselineCommit"] == "abc123"
    assert report["repositories"][0]["headCommit"] == "def456"
    assert report["changeOverview"]["filesChanged"] == 12
    assert report["risks"][0]["level"] == "high"
    assert report["affectedCases"][0]["caseId"] == "ac-1"
    assert report["coverageGaps"][0]["gap"] == "登录失败路径无用例覆盖"


def test_completion_callback_persists_report_readable_via_detail_dump():
    run = make_run(status="success", result_yaml="")
    body = WorkerTaskEventRequest(
        workerId="worker-1",
        taskId="task-1",
        runId="run-1",
        status="success",
        resultYaml=RISK_REPORT_YAML,
    )

    apply_ai_completion_to_run(run, body)

    assert run.result_yaml == RISK_REPORT_YAML
    payload = dump_code_risk_analysis_run(run)
    assert payload["status"] == "success"
    assert payload["report"]["repositories"][0]["headCommit"] == "def456"
    assert payload["report"]["analyzedAt"] == "2026-08-21T10:30:00Z"


def test_completion_callback_reads_report_from_snapshot_fallback():
    run = make_run(status="success", result_yaml="")
    apply_ai_completion_to_run(
        run,
        WorkerTaskEventRequest(
            workerId="worker-1",
            status="success",
            snapshotJson={"resultYaml": RISK_REPORT_YAML},
        ),
    )

    assert dump_code_risk_analysis_run(run)["report"]["risks"][0]["level"] == "high"


@pytest.mark.asyncio
async def test_worker_complete_persists_report_readable_via_detail_dump(monkeypatch):
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
    await WorkerTaskService(FakeRepository()).complete("ai", "worker-task-1", body)

    assert run.result_yaml == RISK_REPORT_YAML
    payload = dump_code_risk_analysis_run(run)
    assert payload["status"] == "success"
    assert payload["report"]["repositories"][0]["baselineCommit"] == "abc123"
    assert payload["report"]["analyzedAt"] == "2026-08-21T10:30:00Z"


class StubCodeRiskAnalysisService:
    async def build_snapshot(
        self, task, run_id, worker_task_id, instruction=None, *, user_id, connection_ids=None
    ):
        return {"taskId": task.task_id, "runId": run_id}


class FakeRunCreateRepository:
    session = AuthorizationDatabase()

    async def get_project(self, project_id):
        return SimpleNamespace(project_id=project_id, user_id="user-1")

    """记录 run/worker 任务创建的服务级仓库桩(工单 07 重复发起口径)。"""

    def __init__(self, task):
        self.task = task
        self.added: list[object] = []
        self.runs: list[AiGenerateTaskRun] = []

    async def get_task(self, task_id):
        assert task_id == self.task.task_id
        return self.task

    def add_all(self, rows):
        self.added.extend(rows)
        self.runs.extend(row for row in rows if isinstance(row, AiGenerateTaskRun))

    async def commit(self):
        return None

    async def refresh(self, row):
        if isinstance(row, AiGenerateTaskRun):
            row.error_message = row.error_message or ""
            row.remediation = row.remediation or ""
            row.result_yaml = row.result_yaml or ""
            row.review_status = row.review_status or "pending"
            row.reviewer_user_id = row.reviewer_user_id or ""
            row.reviewed_at = None
            row.review_comment = row.review_comment or ""
            row.duration_ms = row.duration_ms or 0
            row.import_status = row.import_status or "pending"

    async def list_runs(self, task_id):
        assert task_id == self.task.task_id
        return self.runs


def make_risk_analysis_task() -> SimpleNamespace:
    return SimpleNamespace(
        task_id="task-1",
        task_type="code_risk_analysis",
        name="登录改造 代码风险分析",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="req-1",
        creator_user_id="user-1",
    )


@pytest.mark.asyncio
async def test_repeated_runs_create_distinct_records_without_overwrite():
    repository = FakeRunCreateRepository(make_risk_analysis_task())
    service = AiGenerateTaskService(
        repository, code_risk_analysis_service=StubCodeRiskAnalysisService()
    )
    run_body = {"connectionId": "llm-1", "triggerType": "manual"}

    first = await service.run("code_risk_analysis", "task-1", run_body, "user-1")
    second = await service.run("code_risk_analysis", "task-1", run_body, "user-1")

    assert first["runId"] != second["runId"]
    worker_tasks = [row for row in repository.added if isinstance(row, WorkerTask)]
    assert len(worker_tasks) == 2
    assert worker_tasks[0].task_id != worker_tasks[1].task_id

    listed = await service.list_runs("code_risk_analysis", "task-1", "user-1")
    assert listed["total"] == 2
    assert [item["runId"] for item in listed["items"]] == [first["runId"], second["runId"]]
    assert listed["items"][0]["status"] == "pending"
    assert listed["items"][0]["report"] is None


@pytest.mark.asyncio
async def test_list_runs_dumps_report_for_code_risk_analysis():
    repository = FakeRunCreateRepository(make_risk_analysis_task())
    service = AiGenerateTaskService(
        repository, code_risk_analysis_service=StubCodeRiskAnalysisService()
    )
    await service.run("code_risk_analysis", "task-1", {"connectionId": "llm-1"}, "user-1")
    repository.runs[0].result_yaml = RISK_REPORT_YAML

    listed = await service.list_runs("code_risk_analysis", "task-1", "user-1")

    report = listed["items"][0]["report"]
    assert report["repositories"][0]["baselineCommit"] == "abc123"
    assert report["analyzedAt"] == "2026-08-21T10:30:00Z"


# ---------------------------------------------------------------------------
# HTTP 端点
# ---------------------------------------------------------------------------


def worker_settings() -> Settings:
    return Settings(
        env="test",
        http_host="127.0.0.1",
        http_port=8000,
        jwt_key="test-jwt",
        jwt_expire_hours=1,
        integration_key="test-integration",
        worker_key="worker-token",
        database_url="sqlite+aiosqlite:///:memory:",
        uploads_dir="storage/test-uploads",
    )


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
    class FakeAiGenerateTaskService:
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

        async def run(self, kind, task_id, body, user_id):
            self.captured["run"] = (kind, task_id, body, user_id)
            assert body["connectionId"] == "llm-1"
            return dump_run(
                make_run(
                    status="pending",
                    error_message="",
                    remediation="",
                    snapshot_json={},
                )
            )

        async def owned_run(self, user_id, run_id, kind):
            assert kind == "code_risk_analysis"
            return make_run(result_yaml=RISK_REPORT_YAML)

        async def list(self, kind, project_id, user_id):
            return {"items": [], "total": 0}

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

        async def list_runs(self, kind, task_id, user_id):
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
    fake = FakeAiGenerateTaskService()
    app.dependency_overrides[get_ai_generate_task_service] = lambda: fake
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
    listed_report = runs.json()["data"]["items"][0]["report"]
    assert listed_report["risks"][0]["level"] == "high"

    run_detail = client.get("/v1/code-risk-analysis-runs/run-1")
    assert run_detail.status_code == 200
    detail = run_detail.json()["data"]
    assert detail["status"] == "failed"
    assert detail["errorMessage"] == "GitLab 基线分支已删除"
    assert detail["remediation"] == "请在仓库设置中恢复基线分支或重新绑定"
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


@pytest.fixture(autouse=True)
def worker_contract_authority(monkeypatch):
    """Queue payload unit tests supply an authorized dispatch.

    Actual membership, actor and revocation checks use real HTTP/database tests in
    test_project_membership_api.py, not these fake queue repositories.
    """

    async def authority(session, task, *, pending=False):
        return SimpleNamespace(actor="user-1", project_id="project-1")

    monkeypatch.setattr(worker_task_service_module, "authorize_execution", authority)
