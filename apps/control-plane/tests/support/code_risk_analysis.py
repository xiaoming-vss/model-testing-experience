from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest

from support.ai_execution import AsyncSessionAdapter, seed_task
from support.generation import generation_services
from support.requirement_versions import material_artifact
from testing_agent.core.config import Settings
from testing_agent.core.errors import AppError
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.requirement_software_repository import (
    RequirementRepositoryBinding,
)
from testing_agent.services import worker_task as worker_task_service_module
from testing_agent.services.code_risk_analysis import (
    CodeRiskAnalysisService,
    parse_risk_report,
)

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


def dump_run(run) -> dict:
    summary = run.result_summary_json or {}
    if isinstance(summary, dict) and isinstance(summary.get("uiSemanticReview"), dict):
        review = summary["uiSemanticReview"]
        digest = sha256((run.result_yaml or "").encode("utf-8")).hexdigest()
        if review.get("artifactSha256") != digest:
            summary = {**summary, "uiSemanticReview": {**review, "status": "stale"}}
    return {
        "createdAt": run.created_at,
        "startedAt": run.started_at,
        "finishedAt": run.finished_at,
        "updatedAt": run.history_updated_at,
        "hasResult": bool(run.result_yaml),
        "availableArtifacts": [],
        "runId": run.run_id,
        "taskId": run.task_id,
        "requirementId": run.requirement_id,
        "sprintId": run.sprint_id,
        "projectId": run.project_id,
        "triggerUserId": run.trigger_user_id,
        "triggerType": run.trigger_type,
        "status": run.status,
        "workflowVersion": (run.snapshot_json or {}).get("workflowVersion", 2),
        "checkpointEnabled": run.checkpoint_enabled,
        "generationChainManaged": bool((run.snapshot_json or {}).get("generationChainManaged")),
        "currentStage": run.current_stage,
        "stageStatus": run.stage_status,
        "snapshotJson": run.snapshot_json or {},
        "errorMessage": run.error_message,
        "configJson": run.config_json or {},
        "resultYaml": run.result_yaml,
        "resultSummaryJson": summary,
        "reviewStatus": run.review_status,
        "importStatus": run.import_status,
        "importedTargets": run.imported_targets or [],
        "importedAt": run.imported_at,
        "reviewerUserId": run.reviewer_user_id,
        "reviewedAt": run.reviewed_at,
        "reviewComment": run.review_comment,
        "durationMs": run.duration_ms,
    }


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

    return SimpleNamespace(
        version_id="sv-understanding-1",
        version_no=1,
        task_id="understanding-task",
        attempt_id="understanding-attempt",
        stage="extracting_text",
        artifact_content=content
        if content is not None
        else json.dumps(material_artifact(), ensure_ascii=False),
    )


@pytest.fixture(autouse=True)
def approved_understanding(monkeypatch):
    """Provide an adopted material to snapshot tests unless explicitly omitted."""
    from testing_agent.services.generation_current_material import CurrentMaterial

    material = CurrentMaterial(
        candidate_id="candidate",
        snapshot_id="snapshot",
        candidate_token="token",
        current_token="current-token",
        task_id="understanding-task",
        attempt_id="understanding-attempt",
        content=json.dumps(material_artifact(), ensure_ascii=False),
        content_hash="hash",
        basis_hash="basis",
        lineage_hash="lineage",
        document_root_hash="document",
    )
    original = CodeRiskAnalysisService.build_snapshot

    async def build_with_material(self, *args, **kwargs):
        kwargs.setdefault("current_material", material)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(CodeRiskAnalysisService, "build_snapshot", build_with_material)
    return material


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
) -> RequirementRepositoryBinding:
    return RequirementRepositoryBinding(
        association=SimpleNamespace(
            requirement_id="req-1",
            software_repository_id=binding_id,
            branch=branch,
            baseline_branch=baseline_branch,
        ),
        software_repository=SimpleNamespace(
            software_repository_id=binding_id,
            name=f"仓库 {repository_id}",
            repository_project_id=repository_id,
            repository_group_id=group_id,
            repository_instance_key="gitlab-example",
            repository_instance_url="https://gitlab.example.com",
            repository_path=f"team/{repository_id}",
        ),
    )


def make_connection(connection_id: str, base_url: str, encrypted_token: str) -> SimpleNamespace:
    return SimpleNamespace(
        connection_id=connection_id,
        provider="gitlab",
        project_id="project-1",
        base_url=base_url,
        access_token=encrypted_token,
        extra_json=None,
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


class FakeRequirementRepository:
    def __init__(self, bindings: list):
        self.bindings = bindings

    async def list_for_requirement_with_repository(self, requirement_id: str):
        return self.bindings


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
        self,
        base_url,
        access_token,
        repository_id,
        *,
        search="",
        page=1,
        page_size=100,
        allow_http=False,
        insecure_skip_verify=False,
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
        FakeRequirementRepository(bindings),
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
        current_material=None,
    ):
        return {
            "taskId": task.task_id,
            "runId": run_id,
            "requirementMaterialCurrent": {"candidateId": current_material.candidate_id},
        }


def real_risk_service(session_db):
    from sqlalchemy import select

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository

    seed_task(session_db)
    session_db.add(
        AiGenerateTask(
            task_id="understanding-r",
            task_type="requirement_analysis",
            name="需求分析",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="requirement",
            source_content="",
        )
    )
    session_db.flush()
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
        integration_key="test-integration",
        worker_key="worker-token",
        database_url="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture(autouse=True)
def worker_contract_authority(monkeypatch):
    """Queue payload unit tests supply an authorized dispatch.

    Actual membership, actor and revocation checks use real HTTP/database tests in
    test_project_membership_api.py, not these fake queue repositories.
    """

    async def authority(session, task, *, pending=False):
        return SimpleNamespace(actor="user-1", project_id="project-1")

    monkeypatch.setattr(worker_task_service_module, "authorize_execution", authority)
