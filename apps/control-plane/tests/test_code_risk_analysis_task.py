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
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.generation import generation_services
from support.requirement_versions import material_artifact

from testing_agent.api.deps import (
    get_current_user_id,
    get_generation_launcher,
    get_generation_queries,
    get_generation_task_commands,
    get_worker_task_service,
)
from testing_agent.app import create_app
from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import AppError
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import WorkerTaskEventRequest
from testing_agent.services import worker_task as worker_task_service_module
from testing_agent.services.ai_task_output import dump_run
from testing_agent.services.code_risk_analysis import (
    FUNCTION_CASE_NO_RUN_NOTE,
    CodeRiskAnalysisService,
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


def dump_code_risk_analysis_run(run):
    payload = dump_run(run)
    payload["report"] = parse_risk_report(str(run.result_yaml or ""))
    return payload


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


def understanding_version(content: str | None = None) -> SimpleNamespace:
    from support.requirement_versions import material_artifact

    return SimpleNamespace(
        version_id="sv-understanding-1",
        version_no=1,
        task_id="understanding-task",
        attempt_id="understanding-attempt",
        stage="feature_understanding",
        artifact_content=content
        if content is not None
        else json.dumps(material_artifact(), ensure_ascii=False),
    )


@pytest.fixture(autouse=True)
def approved_understanding(monkeypatch):
    """代码风险分析读取已审核的需求理解版本；快照测试用固定版本替身。"""
    from testing_agent.services import code_risk_analysis as module

    version = understanding_version()

    async def resolve(repository, requirement_id, version_id=""):
        return version

    monkeypatch.setattr(module, "approved_material", resolve)
    return version


def make_requirement() -> SimpleNamespace:
    return SimpleNamespace(
        requirement_id="req-1",
        name="登录改造",
        document_type="richtext",
        document_content="登录模块需求正文",
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
        self.session = SimpleNamespace()

    async def get_requirement(self, requirement_id: str):
        return self.requirement

    async def list_requirement_case_pairs(self, requirement_id, kind):
        rows = {
            "function": self.function_suites,
            "api": self.api_collections,
            "ui": self.ui_suites,
        }[kind]
        key = "collection" if kind == "api" else "suite"
        return [(case, row[key]) for row in rows for case in row["cases"]]

    async def list_api_assert_rules_for_cases(self, case_ids):
        return [
            SimpleNamespace(**{**vars(rule), "case_id": case_id})
            for case_id in case_ids
            for rule in self.api_rules.get(case_id, [])
        ]

    async def latest_case_run_summaries(self, case_ids, kind):
        rows = self.api_collections if kind == "api" else self.ui_suites
        return {
            case.case_id: case.latest_run
            for row in rows
            for case in row["cases"]
            if case.case_id in case_ids
        }


class FakeBindingRepository:
    def __init__(self, bindings: list, group_bindings: dict[str, SimpleNamespace] | None = None):
        self.bindings = bindings
        self.group_bindings = group_bindings or {}

    async def list_active_repo_bindings_for_requirement(self, requirement_id: str):
        return self.bindings

    async def get_active_project_group_binding(self, provider, project_id, group_id, instance=""):
        return self.group_bindings.get(group_id)


class FakeIntegrationConnectionService:
    def __init__(
        self,
        connections: list,
        branches: list | None = None,
        commits: dict[str, str] | None = None,
    ):
        self.connections = {c.connection_id: c for c in connections}
        self.calls: list[dict] = []
        self.gitlab_resource_client = SimpleNamespace(
            list_repository_branches=self._list_repository_branches
        )
        self.branches = branches
        self.commits = commits or {"release-1.0": "abc123", "develop": "def456"}

    async def resolve_personal_connection(
        self, user_id, provider, project_id, instance_url, connection_id=""
    ):
        assert user_id == "user-1"
        connection = next(
            (c for c in self.connections.values() if c.base_url == instance_url),
            None,
        )
        if connection is None:
            raise ValueError("GitLab connection unavailable")
        return connection

    async def get_gitlab_project(self, connection_id, project_id, repository_id, *, user_id):
        self.calls.append(
            {
                "kind": "project",
                "connection_id": connection_id,
                "project_id": project_id,
                "repository_id": repository_id,
            }
        )
        connection = self.connections[connection_id]
        return {
            "id": repository_id,
            "pathWithNamespace": f"team/{repository_id}",
            "cloneUrl": f"{connection.base_url}/team/{repository_id}.git",
            "defaultBranch": "main",
        }

    async def resolve_gitlab_commit(
        self, connection_id, project_id, repository_id, ref, *, user_id
    ):
        self.calls.append(
            {
                "kind": "commit",
                "connection_id": connection_id,
                "project_id": project_id,
                "repository_id": repository_id,
                "ref": ref,
            }
        )
        return self.commits.get(ref, f"sha-{ref}")

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
    connections: list | None = None,
    branches: list | None = None,
    tokens: dict | None = None,
    requirement: SimpleNamespace | None = None,
    task_repository: FakeTaskRepository | None = None,
) -> tuple[CodeRiskAnalysisService, FakeIntegrationConnectionService]:
    bindings = bindings if bindings is not None else []
    integration = FakeIntegrationConnectionService(connections or [], branches)
    service = CodeRiskAnalysisService(
        task_repository or FakeTaskRepository(requirement or make_requirement()),
        FakeBindingRepository(bindings, group_bindings or {}),
        integration,
        FakeCipher(tokens or {}),
    )
    return service, integration


def make_ready_service(
    requirement: SimpleNamespace | None = None,
) -> tuple[CodeRiskAnalysisService, FakeIntegrationConnectionService]:
    """Service with one bound repository and a resolvable personal connection."""
    return make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1")],
        group_bindings={"group-1": SimpleNamespace(connection_id="conn-1")},
        connections=[make_connection("conn-1", "https://gitlab.example.com", "enc:token-1")],
        tokens={"enc:token-1": "plain-token-1"},
        requirement=requirement,
    )


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
        "config_json": {},
        "result_yaml": "",
        "result_summary_json": {},
        "review_status": "pending",
        "reviewer_user_id": "",
        "reviewed_at": None,
        "review_comment": "",
        "duration_ms": 0,
        "created_at": None,
        "started_at": None,
        "finished_at": None,
        "history_updated_at": None,
        "import_status": "pending",
        "imported_targets": [],
        "imported_at": None,
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
    assert snapshot["requirementMaterialVersion"] == {
        "versionId": "sv-understanding-1",
        "versionNo": 1,
        "taskId": "understanding-task",
        "runId": "understanding-attempt",
    }
    entry = snapshot["bindings"][0]
    assert entry["bindingId"] == "binding-1"
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

    assert "尚未绑定代码仓库" in str(error.value)


@pytest.mark.asyncio
async def test_missing_approved_understanding_rejects_the_run(monkeypatch):
    from testing_agent.services import code_risk_analysis as module

    async def missing(repository, requirement_id, version_id=""):
        return None

    monkeypatch.setattr(module, "approved_material", missing)
    service, _ = make_service()

    with pytest.raises(AppError) as error:
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert "请先审核通过材料整理" in str(error.value)


@pytest.mark.asyncio
async def test_explicit_understanding_version_is_forwarded(monkeypatch):
    from testing_agent.services import code_risk_analysis as module

    requested = {}

    async def resolve(repository, requirement_id, version_id=""):
        requested["version_id"] = version_id
        return understanding_version()

    monkeypatch.setattr(module, "approved_material", resolve)
    service, _ = make_ready_service()

    await service.build_snapshot(
        make_task(), "run-1", "worker-task-1", user_id="user-1", material_version_id="sv-old"
    )

    assert requested["version_id"] == "sv-old"


@pytest.mark.asyncio
async def test_build_snapshot_freezes_clone_url_and_pinned_commits():
    binding = make_binding("binding-1", "repo-1", "group-1", baseline_branch="release-1.0")
    connection = make_connection("conn-1", "https://gitlab.example.com", "enc:token-1")
    service, integration = make_service(
        bindings=[binding],
        group_bindings={"group-1": SimpleNamespace(connection_id="conn-1")},
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
        group_bindings={"group-1": SimpleNamespace(connection_id="conn-1")},
        connections=[connection],
        tokens={"enc:token-1": "plain-token-1"},
    )

    with pytest.raises(AppError) as error:
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert "选择基线分支" in str(error.value)


@pytest.mark.asyncio
async def test_branch_checker_raises_when_repo_has_no_resolved_connection():
    service, _ = make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1")],
    )

    with pytest.raises((AppError, ValueError)):
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")


@pytest.mark.asyncio
async def test_missing_group_binding_marks_binding_connection_unresolved():
    binding = make_binding("binding-1", "repo-1", "group-missing")
    service, _ = make_service(bindings=[binding])

    with pytest.raises((AppError, ValueError)):
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")


@pytest.mark.asyncio
async def test_decrypt_failure_treats_binding_as_connection_unresolved():
    connection = make_connection("conn-1", "https://gitlab.example.com", "enc:broken")
    service, _ = make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1")],
        group_bindings={"group-1": SimpleNamespace(connection_id="conn-1")},
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
    direct = SimpleNamespace(
        is_direct=AsyncMock(return_value=True),
        authorize=AsyncMock(
            return_value=SimpleNamespace(
                actor_id="actor",
                task=SimpleNamespace(project_id="project-1"),
                input_snapshot={"source": {"bindings": [{"repositoryId": "repo-1"}]}},
            )
        ),
    )
    monkeypatch.setattr(worker_task_service_module, "DirectStageWorkerService", lambda _: direct)

    payload = await WorkerTaskService(FakeRepository()).gitlab_credentials("worker-task-1")
    assert payload["taskId"] == "worker-task-1"


@pytest.mark.asyncio
async def test_worker_requirement_document_allows_code_risk_analysis(monkeypatch):
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
                document_file_id="stored-requirement",
                document_content="需求正文",
                document_filename="",
            )

    direct = SimpleNamespace(
        is_direct=AsyncMock(return_value=True),
        authorize=AsyncMock(
            return_value=SimpleNamespace(
                task=SimpleNamespace(requirement_id="req-1"), input_snapshot={}
            )
        ),
    )
    monkeypatch.setattr(worker_task_service_module, "DirectStageWorkerService", lambda _: direct)
    requirement = await WorkerTaskService(FakeRepository()).requirement_document("worker-task-1")
    assert requirement.document_content == "需求正文"


# ---------------------------------------------------------------------------
# 失败错误消息与补救建议回显
# ---------------------------------------------------------------------------


def test_parse_risk_report_reads_context_preview_receipt():
    report = parse_risk_report(
        """\
analyzedAt: "2026-08-27T10:00:00Z"
contextReceipt:
  mode: context_preview
  repositories:
    - repositoryId: "repo-1"
      headCommit: "def456"
  counts:
    repositories: 1
    changedFiles: 2
    diffChars: 123
  truncatedFiles: ["src/big.py"]
  summary: "已读取仓库上下文"
  filesRead: ["src/login.py"]
  toolsUsed: ["read"]
"""
    )

    assert report["analyzedAt"] == "2026-08-27T10:00:00Z"
    assert report["repositories"] == [{"repositoryId": "repo-1", "headCommit": "def456"}]
    assert report["contextReceipt"]["mode"] == "context_preview"
    assert report["contextReceipt"]["counts"]["diffChars"] == 123
    assert report["contextReceipt"]["truncatedFiles"] == ["src/big.py"]
    assert report["contextReceipt"]["summary"] == "已读取仓库上下文"
    assert "risks" not in report

    snake = parse_risk_report("context_receipt:\n  summary: snake\n")
    assert snake["contextReceipt"]["summary"] == "snake"
    assert snake["repositories"] == []


def test_parse_risk_report_rejects_malformed_context_receipt():
    for raw in (
        "contextReceipt: []\n",
        "contextReceipt:\n  repositories: not-a-list\n",
        "contextReceipt:\n  repositories:\n    - not-an-object\n",
        "analyzedAt: 2026-08-27\ncontextReceipt: {}\n",
    ):
        assert parse_risk_report(raw) is None


def test_dump_code_risk_analysis_run_includes_context_receipt():
    receipt_yaml = (
        "analyzedAt: '2026-08-27T10:00:00Z'\n"
        "contextReceipt:\n"
        "  mode: context_preview\n"
        "  repositories: []\n"
        "  counts: {repositories: 0}\n"
        "  summary: preview\n"
    )
    payload = dump_code_risk_analysis_run(make_run(status="success", result_yaml=receipt_yaml))

    assert payload["report"]["contextReceipt"]["mode"] == "context_preview"
    assert payload["report"]["repositories"] == []


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


class StubCodeRiskAnalysisService:
    async def build_snapshot(
        self,
        task,
        run_id,
        worker_task_id,
        instruction=None,
        *,
        user_id,
        connection_ids=None,
        material_version_id="",
    ):
        return {
            "taskId": task.task_id,
            "runId": run_id,
            "requirementMaterialVersion": {"versionId": "understanding-r-v1"},
        }


def real_risk_service(session_db):
    from sqlalchemy import select

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository

    seed_task(session_db)
    from support.requirement_versions import material_version

    material_version(session_db)
    task = session_db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "code_risk_analysis"
    session_db.commit()
    repository = AiGenerateTaskRepository(AsyncSessionAdapter(session_db))
    return generation_services(repository, code_risk_analysis_service=StubCodeRiskAnalysisService())


@pytest.mark.asyncio
async def test_repeated_runs_create_distinct_records_without_overwrite(db):  # noqa: F811
    from sqlalchemy import select

    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions

    service = real_risk_service(db)
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


@pytest.fixture(autouse=True)
def worker_contract_authority(monkeypatch):
    """Queue payload unit tests supply an authorized dispatch.

    Actual membership, actor and revocation checks use real HTTP/database tests in
    test_project_membership_api.py, not these fake queue repositories.
    """

    async def authority(session, task, *, pending=False):
        return SimpleNamespace(actor="user-1", project_id="project-1")

    monkeypatch.setattr(worker_task_service_module, "authorize_execution", authority)
