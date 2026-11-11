"""UI generation source resolution from repository profile versions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.schemas.generation_chain import GenerationChainRunRequest
from testing_agent.services.repo_gitlab_access import RepoGitlabAccess
from testing_agent.services.stage_storage.authorization import DirectWorkerAuthority
from testing_agent.services.stage_storage.payload import worker_payloads
from testing_agent.services.ui_generation_source import (
    ResolvedUiSource,
    UiGenerationSourceService,
)


def repository_profile(*repositories: dict) -> dict:
    return {"repositories": list(repositories), "overallSummary": "需求主要涉及前端"}


def profile_repository(
    repository_id: str,
    role: str,
    *,
    confidence: float = 0.9,
    path: str | None = None,
) -> dict:
    return {
        "repositoryId": repository_id,
        "pathWithNamespace": path or f"team/{repository_id}",
        "role": role,
        "responsibilitySummary": f"{repository_id} 的职责",
        "techStack": ["React"],
        "keyPaths": ["src"],
        "confidence": confidence,
        "evidence": ["package.json"],
    }


def seed_profile(
    session,
    profiles: list[tuple[dict, list[dict]]],
    *,
    branch: str = "main",
    head_commit: str = "sha-profile",
):
    seed_task(session)
    task = session.query(AiGenerateTask).filter_by(task_id="task").one()
    task.task_type = "repository_profile"
    stage = AiGenerationStage(
        id="profile-stage", task_id=task.task_id, stage="generate", next_version_no=1
    )
    session.add(stage)
    session.flush()
    for index, (profile, bindings) in enumerate(profiles, start=1):
        session.add(
            AiGenerationAttempt(
                id=f"profile-attempt-{index}",
                stage_id=stage.id,
                attempt_no=index,
                operation="generate",
                status="success",
                output_content=json.dumps(profile, ensure_ascii=False),
                output_format="json",
                input_snapshot_json={"source": {"bindings": bindings}},
                finished_at=datetime(2026, 1, index, tzinfo=UTC),
            )
        )
    session.add(
        ResourceBinding(
            binding_id="binding-1",
            user_id="u",
            provider="gitlab",
            instance_url="https://gitlab.example.com",
            instance_key="gitlab",
            connection_id="profile-conn",
            local_resource_type="requirement",
            local_resource_id="r",
            remote_resource_type="repository",
            remote_resource_id="repo-front",
            remote_parent_id="group-1",
            remote_name_snapshot="team/repo-front",
            status="active",
            extra_json={"branch": branch},
        )
    )
    session.commit()
    return task, branch, head_commit


def profile_binding(repository_id: str = "repo-front", *, commit: str = "sha-profile") -> dict:
    return {
        "bindingId": "binding-1",
        "repositoryId": repository_id,
        "instanceUrl": "https://gitlab.example.com",
        "pathWithNamespace": f"team/{repository_id}",
        "branch": "main",
        "headCommit": commit,
        "cloneUrl": f"https://gitlab.example.com/team/{repository_id}.git",
        "connectionId": "profile-conn",
        "profileError": "",
    }


def ui_binding() -> dict:
    return {**profile_binding(), "connectionId": "ui-conn"}


def source_service(
    session, *, head_commit: str = "sha-head"
) -> tuple[UiGenerationSourceService, SimpleNamespace]:
    connections = SimpleNamespace(
        get_gitlab_project=AsyncMock(
            return_value={
                "cloneUrl": "https://gitlab.example.com/team/repo-front.git",
                "pathWithNamespace": "team/repo-front",
            }
        ),
        resolve_gitlab_commit=AsyncMock(return_value=head_commit),
    )
    service = UiGenerationSourceService(
        AsyncSessionAdapter(session),
        binding_repository=ResourceBindingRepository(AsyncSessionAdapter(session)),
        integration_connection_service=connections,
        credential_cipher=None,
    )
    return service, connections


@pytest.fixture(autouse=True)
def ui_access(monkeypatch):
    from testing_agent.services import ui_generation_source as module

    monkeypatch.setattr(
        module,
        "resolve_repo_gitlab_access",
        AsyncMock(return_value=RepoGitlabAccess("ui-conn", "https://gitlab.example.com", "token")),
    )


async def test_options_expose_frontend_candidates_and_default_latest(db):  # noqa: F811
    seed_profile(
        db,
        [
            (
                repository_profile(
                    profile_repository("repo-front", "frontend", confidence=0.7),
                    profile_repository("repo-back", "backend", confidence=0.99),
                ),
                [
                    profile_binding("repo-front", commit="sha-old"),
                    {**profile_binding("repo-back"), "headCommit": "sha-back"},
                ],
            ),
            (
                repository_profile(profile_repository("repo-front", "frontend", confidence=0.91)),
                [profile_binding("repo-front", commit="sha-new")],
            ),
        ],
    )
    service, _ = source_service(db)
    options = await service.options("r")

    assert options["defaultProfileVersionId"] == "profile-attempt-2"
    assert options["defaultRepositoryId"] == "repo-front"
    assert [item["versionId"] for item in options["profileVersions"]] == [
        "profile-attempt-2",
        "profile-attempt-1",
    ]
    latest = options["profileVersions"][0]
    assert latest["versionNo"] == 2
    assert latest["repositories"][0]["isFrontend"] is True
    assert latest["repositories"][0]["available"] is True
    assert latest["repositories"][0]["commit"] == "sha-new"
    assert latest["repositories"][0]["branch"] == "main"
    assert "cloneUrl" not in latest["repositories"][0]
    assert "connectionId" not in latest["repositories"][0]


async def test_options_return_empty_without_profile_task(db):  # noqa: F811
    seed_task(db)
    service, _ = source_service(db)
    assert await service.options("r") == {
        "profileVersions": [],
        "defaultProfileVersionId": "",
        "defaultRepositoryId": "",
    }


async def test_resolve_profile_pin_uses_ui_initiator_connection(db):  # noqa: F811
    seed_profile(
        db,
        [
            (
                repository_profile(profile_repository("repo-front", "frontend")),
                [profile_binding()],
            )
        ],
    )
    service, connections = source_service(db)
    resolved = await service.resolve(
        requirement_id="r",
        project_id="p",
        user_id="u",
        profile_version_id="profile-attempt-1",
        repository_id="repo-front",
    )

    assert resolved.profile_version_no == 1
    assert resolved.repository["commit"] == "sha-profile"
    assert resolved.repository["commitMode"] == "profile"
    assert resolved.binding["connectionId"] == "ui-conn"
    assert resolved.binding["headCommit"] == "sha-profile"
    connections.resolve_gitlab_commit.assert_not_called()
    connections.get_gitlab_project.assert_awaited_once_with(
        "ui-conn", "p", "repo-front", user_id="u"
    )


async def test_resolve_latest_head_freezes_resolved_sha(db):  # noqa: F811
    seed_profile(
        db,
        [
            (
                repository_profile(profile_repository("repo-front", "frontend")),
                [profile_binding()],
            )
        ],
    )
    service, connections = source_service(db, head_commit="sha-head")
    resolved = await service.resolve(
        requirement_id="r",
        project_id="p",
        user_id="u",
        profile_version_id="profile-attempt-1",
        repository_id="repo-front",
        commit_mode="latest",
    )

    assert resolved.repository["commit"] == "sha-head"
    assert resolved.repository["commitMode"] == "latest"
    assert resolved.binding["headCommit"] == "sha-head"
    connections.resolve_gitlab_commit.assert_awaited_once_with(
        "ui-conn", "p", "repo-front", "main", user_id="u"
    )


async def test_resolve_rejects_missing_profile_and_non_frontend(db):  # noqa: F811
    service, _ = source_service(db)
    with pytest.raises(AppError, match="请先生成仓库画像"):
        await service.resolve(
            requirement_id="r",
            project_id="p",
            user_id="u",
            profile_version_id="missing",
            repository_id="repo-front",
        )

    seed_profile(
        db,
        [
            (
                repository_profile(profile_repository("repo-back", "backend")),
                [profile_binding("repo-back")],
            )
        ],
    )
    service, _ = source_service(db)
    with pytest.raises(AppError, match="不是前端或全栈仓库"):
        await service.resolve(
            requirement_id="r",
            project_id="p",
            user_id="u",
            profile_version_id="profile-attempt-1",
            repository_id="repo-back",
        )


async def test_resolve_rejects_binding_profile_error(db):  # noqa: F811
    seed_profile(
        db,
        [
            (
                repository_profile(profile_repository("repo-front", "frontend")),
                [{**profile_binding(), "profileError": "GitLab 仓库不可访问"}],
            )
        ],
    )
    service, _ = source_service(db)
    with pytest.raises(AppError, match="GitLab 仓库不可访问"):
        await service.resolve(
            requirement_id="r",
            project_id="p",
            user_id="u",
            profile_version_id="profile-attempt-1",
            repository_id="repo-front",
        )


async def test_source_check_reports_branch_drift_without_mutation(db):  # noqa: F811
    seed_profile(
        db,
        [
            (
                repository_profile(profile_repository("repo-front", "frontend")),
                [profile_binding()],
            )
        ],
    )
    service, connections = source_service(db, head_commit="sha-new-head")
    result = await service.check(
        requirement_id="r",
        project_id="p",
        user_id="u",
        profile_version_id="profile-attempt-1",
        repository_id="repo-front",
        pinned_commit="sha-profile",
    )
    assert result == {
        "repositoryId": "repo-front",
        "branch": "main",
        "pinnedCommit": "sha-profile",
        "currentCommit": "sha-new-head",
        "changed": True,
    }
    connections.resolve_gitlab_commit.assert_awaited_once()


def seed_ui_task(session, *, case_contents: list[dict] | None = None):
    seed_task(session)
    task = session.query(AiGenerateTask).filter_by(task_id="task").one()
    task.task_type = "ui_case_generate"
    task.source_type = "repository"
    session.add(
        AiGenerationStage(
            id="ui-surface", task_id=task.task_id, stage="ui_surface", next_version_no=1
        )
    )
    session.add(FunctionTestSuite(suite_id="suite", requirement_id="r", name="功能"))
    session.flush()
    for index, content in enumerate(
        case_contents or [{"preconditions": [], "steps": [{"action": "打开", "expected": "显示"}]}]
    ):
        session.add(
            FunctionTestCase(
                case_id=f"C{index + 1}",
                suite_id="suite",
                title=f"用例{index + 1}",
                content=content,
            )
        )
    session.commit()
    return task


async def test_start_ui_surface_freezes_repository_and_worker_payload(db, monkeypatch):  # noqa: F811
    from support.generation import generation_services

    from testing_agent.services.stage_storage import run_command

    task = seed_ui_task(db)
    session = AsyncSessionAdapter(db)
    bundle = generation_services(AiGenerateTaskRepository(session))
    resolved = ResolvedUiSource(
        profile_version_id="profile-attempt-1",
        profile_version_no=1,
        repository={
            "bindingId": "binding-1",
            "repositoryId": "repo-front",
            "instanceUrl": "https://gitlab.example.com",
            "pathWithNamespace": "team/repo-front",
            "branch": "main",
            "commit": "sha-profile",
            "commitMode": "latest",
            "resolvedAt": "2026-11-09T00:00:00+00:00",
        },
        binding={
            "bindingId": "binding-1",
            "repositoryId": "repo-front",
            "instanceUrl": "https://gitlab.example.com",
            "pathWithNamespace": "team/repo-front",
            "branch": "main",
            "headCommit": "sha-profile",
            "cloneUrl": "https://gitlab.example.com/team/repo-front.git",
            "connectionId": "ui-conn",
            "profileError": "",
        },
    )
    bundle.chain.ui_sources.resolve = AsyncMock(return_value=resolved)
    monkeypatch.setattr(run_command, "require_personal_connection", AsyncMock())

    attempt = await run_command.start_stage(
        bundle.chain,
        task,
        "ui",
        "ui_surface",
        GenerationChainRunRequest(
            connectionId="llm",
            functionCaseIds=["C1"],
            sourceProfileVersionId="profile-attempt-1",
            sourceRepositoryId="repo-front",
            sourceCommitMode="latest",
            gitlabConnectionId="ui-conn",
        ),
        "u",
    )

    bundle.chain.ui_sources.resolve.assert_awaited_once_with(
        requirement_id="r",
        project_id="p",
        user_id="u",
        profile_version_id="profile-attempt-1",
        repository_id="repo-front",
        commit_mode="latest",
        gitlab_connection_id="ui-conn",
    )
    source = attempt.input_snapshot_json["source"]
    assert source["sourceKind"] == "repository"
    assert source["sourceType"] == "repository"
    assert source["sourceProfileVersionId"] == "profile-attempt-1"
    assert source["sourceProfileVersionNo"] == 1
    assert source["sourceRepository"]["commit"] == "sha-profile"
    assert source["sourceRepository"]["commitMode"] == "latest"
    assert source["bindings"][0]["connectionId"] == "ui-conn"
    assert source["functionalCases"][0]["caseId"] == "C1"
    assert "sourceArchiveFileId" not in source
    assert task.source_type == "repository"

    queue = WorkerTask(
        domain="ai",
        task_id=attempt.worker_task_id,
        task_type="ui_case_generate",
        run_id=attempt.id,
        status="claimed",
    )
    authority = DirectWorkerAuthority(
        "ui-surface", attempt.id, "u", task, attempt.input_snapshot_json, None
    )
    _, payload = worker_payloads(authority, queue, stage_name="ui_surface", lease_seconds=30)
    run = payload["run"]
    assert run["sourceKind"] == "repository"
    assert run["sourceRepository"]["commit"] == "sha-profile"
    assert run["gitlabCredentialsUrl"] == (
        f"/internal/ai-worker/tasks/{attempt.worker_task_id}/gitlab-credentials"
    )
    assert "sourceArchiveDownloadUrl" not in run


async def test_start_ui_surface_requires_source_fields(db, monkeypatch):  # noqa: F811
    from support.generation import generation_services

    from testing_agent.services.stage_storage import run_command

    task = seed_ui_task(db)
    bundle = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    monkeypatch.setattr(run_command, "require_personal_connection", AsyncMock())
    with pytest.raises(AppError, match="请选择仓库画像版本和前端仓库"):
        await run_command.start_stage(
            bundle.chain,
            task,
            "ui",
            "ui_surface",
            GenerationChainRunRequest(connectionId="llm", functionCaseIds=["C1"]),
            "u",
        )


async def test_chain_view_exposes_repository_source_and_case_drift(db):  # noqa: F811
    from testing_agent.services.stage_storage.chain_view import build_chain_view

    task = seed_ui_task(db)
    stage = db.scalar(select(AiGenerationStage).where(AiGenerationStage.task_id == task.task_id))
    stage.source_batch_id = "batch-1"
    stage.source_snapshot_json = {
        "sourceKind": "repository",
        "sourceType": "repository",
        "sourceProfileVersionId": "profile-attempt-1",
        "sourceProfileVersionNo": 1,
        "sourceRepository": {
            "repositoryId": "repo-front",
            "pathWithNamespace": "team/repo-front",
            "branch": "main",
            "commit": "sha-profile",
            "commitMode": "profile",
            "resolvedAt": "2026-11-09T00:00:00+00:00",
        },
        "bindings": [ui_binding()],
        "functionalCases": [
            {
                "caseId": "C1",
                "suiteId": "suite",
                "suiteName": "功能",
                "module": "",
                "title": "用例1",
                "priority": "",
                "caseType": "",
                "content": {"preconditions": [], "steps": [{"action": "打开", "expected": "显示"}]},
            }
        ],
    }
    db.commit()

    view = await build_chain_view(AsyncSessionAdapter(db), "r", "ui", task, detail=True)
    assert view.source_inputs is not None
    assert view.source_inputs.source_kind == "repository"
    assert view.source_inputs.repository.commit == "sha-profile"
    assert view.source_inputs.repository.profile_version_id == "profile-attempt-1"
    assert view.source_changed is False

    case = db.scalar(select(FunctionTestCase).where(FunctionTestCase.case_id == "C1"))
    case.title = "已修改标题"
    db.commit()
    changed = await build_chain_view(AsyncSessionAdapter(db), "r", "ui", task, detail=True)
    assert changed.source_changed is True


async def test_worker_authorization_rechecks_ui_initiator_gitlab_connection(db, monkeypatch):
    from types import SimpleNamespace

    from testing_agent.services.stage_storage import authorization

    task = seed_ui_task(db)
    stage = db.scalar(select(AiGenerationStage).where(AiGenerationStage.task_id == task.task_id))
    attempt = AiGenerationAttempt(
        id="ui-attempt",
        stage_id=stage.id,
        attempt_no=1,
        operation="generate",
        requested_by="u",
        status="claimed",
        worker_task_id="ui-worker",
        input_snapshot_json={
            "llmConnectionId": "llm",
            "source": {
                "sourceKind": "repository",
                "bindings": [ui_binding()],
            },
        },
    )
    stage.active_attempt_id = attempt.id
    db.add(attempt)
    db.add(
        WorkerTask(
            domain="ai",
            task_id="ui-worker",
            task_type="ui_case_generate",
            run_id=attempt.id,
            status="claimed",
        )
    )
    db.commit()

    project_check = AsyncMock()
    connection_check = AsyncMock(
        return_value=SimpleNamespace(base_url="https://gitlab.example.com")
    )
    monkeypatch.setattr(authorization, "require_project_id", project_check)
    monkeypatch.setattr(authorization, "require_personal_connection", connection_check)
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "ui-worker"))
    authority = await authorization.authorize_stage_worker(AsyncSessionAdapter(db), queue)
    assert authority.actor_id == "u"
    checked = [call.args[3] for call in connection_check.await_args_list]
    assert checked == ["llm", "ui-conn"]

    connection_check.side_effect = AppError(403, "授权已撤销", 403)
    with pytest.raises(AppError):
        await authorization.authorize_stage_worker(AsyncSessionAdapter(db), queue)


async def test_revocation_identity_aggregates_ui_gitlab_connection(db):
    from testing_agent.services.stage_storage.authorization import (
        direct_revocation_identity,
    )

    task = seed_ui_task(db)
    stage = db.scalar(select(AiGenerationStage).where(AiGenerationStage.task_id == task.task_id))
    attempt = AiGenerationAttempt(
        id="ui-attempt",
        stage_id=stage.id,
        attempt_no=1,
        operation="generate",
        requested_by="u",
        status="claimed",
        worker_task_id="ui-worker",
        input_snapshot_json={
            "llmConnectionId": "llm",
            "source": {"bindings": [ui_binding()]},
        },
    )
    db.add(attempt)
    queue = WorkerTask(
        domain="ai",
        task_id="ui-worker",
        task_type="ui_case_generate",
        run_id=attempt.id,
        status="claimed",
    )
    db.add(queue)
    db.commit()
    identity = await direct_revocation_identity(AsyncSessionAdapter(db), queue)
    assert identity is not None
    assert identity.actor_id == "u"
    assert identity.connection_ids == frozenset({"llm", "ui-conn"})


def test_ui_source_routes_replace_archive_endpoints():
    from testing_agent.app import create_app

    paths = create_app().openapi()["paths"]
    assert "get" in paths["/v1/requirements/{requirementId}/generation/ui/source-options"]
    assert "post" in paths["/v1/requirements/{requirementId}/generation/ui/source-check"]
    assert "/v1/ui-case-generate-tasks/{taskId}/source-archive" not in paths
    assert "/internal/ai-worker/tasks/{taskId}/source-archive" not in paths


async def test_source_options_and_check_handlers_return_safe_payloads():
    from types import SimpleNamespace

    from testing_agent.handlers.generation_chain import (
        check_ui_generation_source,
        get_ui_generation_source_options,
    )
    from testing_agent.schemas.generation_chain import UiGenerationSourceCheckRequest

    options = {
        "profileVersions": [
            {
                "versionId": "profile-attempt-1",
                "versionNo": 1,
                "label": "v1",
                "repositories": [
                    {
                        "repositoryId": "repo-front",
                        "role": "frontend",
                        "isFrontend": True,
                        "available": True,
                    }
                ],
                "defaultRepositoryId": "repo-front",
            }
        ],
        "defaultProfileVersionId": "profile-attempt-1",
        "defaultRepositoryId": "repo-front",
    }
    checked = {
        "repositoryId": "repo-front",
        "branch": "main",
        "pinnedCommit": "sha-old",
        "currentCommit": "sha-new",
        "changed": True,
    }
    service = SimpleNamespace(
        scope=AsyncMock(),
        tasks=SimpleNamespace(
            get_requirement=AsyncMock(return_value=SimpleNamespace(sprint_id="s")),
            get_sprint=AsyncMock(return_value=SimpleNamespace(project_id="p")),
        ),
        ui_sources=SimpleNamespace(
            options=AsyncMock(return_value=options),
            check=AsyncMock(return_value=checked),
        ),
    )
    listed = await get_ui_generation_source_options("r", user_id="u", service=service)
    data = listed["data"].model_dump(by_alias=True)
    assert data["defaultProfileVersionId"] == "profile-attempt-1"
    assert data["profileVersions"][0]["repositories"][0]["repositoryId"] == "repo-front"

    result = await check_ui_generation_source(
        "r",
        UiGenerationSourceCheckRequest(
            profileVersionId="profile-attempt-1",
            repositoryId="repo-front",
            pinnedCommit="sha-old",
        ),
        user_id="u",
        service=service,
    )
    assert result["data"].model_dump(by_alias=True) == checked
    service.ui_sources.check.assert_awaited_once_with(
        requirement_id="r",
        project_id="p",
        user_id="u",
        profile_version_id="profile-attempt-1",
        repository_id="repo-front",
        pinned_commit="sha-old",
        gitlab_connection_id="",
    )


async def test_direct_attempt_view_hides_ui_repository_bindings(db):  # noqa: F811
    import json

    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.services.stage_storage.run_view import direct_attempt_view

    task = seed_ui_task(db)
    stage = db.scalar(select(AiGenerationStage).where(AiGenerationStage.task_id == task.task_id))
    attempt = AiGenerationAttempt(
        id="ui-run-view",
        stage_id=stage.id,
        attempt_no=1,
        operation="generate",
        status="pending",
        requested_by="u",
        worker_task_id="ui-worker",
        input_snapshot_json={
            "source": {
                "sourceKind": "repository",
                "sourceProfileVersionId": "profile-attempt-1",
                "sourceProfileVersionNo": 1,
                "sourceRepository": {
                    "repositoryId": "repo-front",
                    "pathWithNamespace": "team/repo-front",
                    "branch": "main",
                    "commit": "sha-profile",
                    "commitMode": "profile",
                },
                "bindings": [ui_binding()],
                "functionalCases": [],
            },
            "llmConnectionId": "llm",
        },
    )
    stage.active_attempt_id = attempt.id
    db.add(attempt)
    db.commit()

    view = await direct_attempt_view(AsyncSessionAdapter(db), task.task_id, attempt.id)
    snapshot = view["snapshotJson"]
    assert snapshot["sourceRepository"]["commit"] == "sha-profile"
    assert "bindings" not in snapshot
    assert "bindingId" not in snapshot["sourceRepository"]
    serialized = json.dumps(view, ensure_ascii=False, default=str)
    assert "cloneUrl" not in serialized
    assert "ui-conn" not in serialized
    assert "gitlab.example.com" not in serialized
