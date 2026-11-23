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
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.repo_gitlab_access import RepoGitlabAccess
from testing_agent.services.service_instance import instance_key
from testing_agent.services.ui_generation_source import (
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
    stage = AiGenerationStage(id="profile-stage", task_id=task.task_id, stage="generate")
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
    repository_ids = {
        binding["repositoryId"]
        for _, bindings in profiles
        for binding in bindings
        if binding.get("repositoryId")
    }
    for repository_id in repository_ids:
        session.add(
            SoftwareRepository(
                software_repository_id=repository_id,
                project_id="p",
                name=repository_id,
                description="",
                base_path="",
                repository_project_id=repository_id,
                repository_group_id="group-1",
                repository_instance_key=instance_key("https://gitlab.example.com"),
                repository_path=f"team/{repository_id}",
                repository_name=repository_id,
                repository_instance_url="https://gitlab.example.com",
                version=1,
                created_by_user_id="u",
            )
        )
    session.commit()
    return task, branch, head_commit


def profile_binding(repository_id: str = "repo-front", *, commit: str = "sha-profile") -> dict:
    return {
        "bindingId": "binding-1",
        "softwareRepositoryId": repository_id,
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
        integration_connection_service=connections,
        credential_cipher=None,
    )
    return service, connections


async def test_resolve_current_profile_freezes_pin_with_initiators_access(db):  # noqa: F811
    seed_profile(
        db,
        [(repository_profile(profile_repository("repo-front", "frontend")), [profile_binding()])],
    )
    service, connections = source_service(db)
    current = SimpleNamespace(
        candidate_id="candidate-a",
        profile=repository_profile(profile_repository("repo-front", "frontend")),
        bindings=[profile_binding()],
    )
    resolved = await service.resolve_current(
        current=current,
        project_id="p",
        user_id="u",
        repository_id="repo-front",
        commit_mode="latest",
        gitlab_connection_id="ui-conn",
    )
    assert resolved.repository["commit"] == "sha-head"
    assert resolved.binding["connectionId"] == "ui-conn"
    connections.get_gitlab_project.assert_awaited_once_with(
        "ui-conn", "p", "repo-front", user_id="u"
    )
    connections.resolve_gitlab_commit.assert_awaited_once()


async def test_resolve_current_profile_rejects_unavailable_repository(db):  # noqa: F811
    seed_task(db)
    service, connections = source_service(db)
    current = SimpleNamespace(
        candidate_id="candidate-a",
        profile=repository_profile(profile_repository("repo-front", "frontend")),
        bindings=[{**profile_binding(), "profileError": "unavailable"}],
    )
    with pytest.raises(AppError):
        await service.resolve_current(
            current=current, project_id="p", user_id="u", repository_id="repo-front"
        )
    connections.get_gitlab_project.assert_not_awaited()


async def test_resolve_current_profile_uses_pinned_commit_and_actor_access(db):  # noqa: F811
    seed_profile(
        db,
        [(repository_profile(profile_repository("repo-front", "frontend")), [profile_binding()])],
    )
    service, connections = source_service(db)
    current = SimpleNamespace(
        candidate_id="candidate-a",
        profile=repository_profile(profile_repository("repo-front", "frontend")),
        bindings=[profile_binding()],
    )
    resolved = await service.resolve_current(
        current=current, project_id="p", user_id="u", repository_id="repo-front"
    )
    assert resolved.repository["commit"] == "sha-profile"
    assert resolved.repository["commitMode"] == "profile"
    assert resolved.binding["connectionId"] == "ui-conn"
    connections.resolve_gitlab_commit.assert_not_called()
    connections.get_gitlab_project.assert_awaited_once_with(
        "ui-conn", "p", "repo-front", user_id="u"
    )


async def test_resolve_current_profile_rejects_non_frontend_repository(db):  # noqa: F811
    seed_task(db)
    service, connections = source_service(db)
    current = SimpleNamespace(
        candidate_id="candidate-a",
        profile=repository_profile(profile_repository("repo-back", "backend")),
        bindings=[profile_binding("repo-back")],
    )
    with pytest.raises(AppError, match="不属于当前画像"):
        await service.resolve_current(
            current=current, project_id="p", user_id="u", repository_id="repo-back"
        )
    connections.get_gitlab_project.assert_not_awaited()


async def test_rebind_frozen_uses_new_actor_and_keeps_original_commit(db):  # noqa: F811
    seed_profile(
        db,
        [(repository_profile(profile_repository("repo-front", "frontend")), [profile_binding()])],
    )
    service, connections = source_service(db)
    pin = {
        "repositoryId": "repo-front",
        "instanceUrl": "https://gitlab.example.com",
        "pathWithNamespace": "team/repo-front",
        "branch": "main",
        "commit": "frozen-commit",
    }
    binding = await service.rebind_frozen(
        repository=pin,
        binding=profile_binding(),
        project_id="p",
        user_id="another-user",
        gitlab_connection_id="ui-conn",
    )
    assert binding["headCommit"] == "frozen-commit"
    assert binding["connectionId"] == "ui-conn"
    connections.get_gitlab_project.assert_awaited_once_with(
        "ui-conn", "p", "repo-front", user_id="another-user"
    )
    connections.resolve_gitlab_commit.assert_not_awaited()
    connections.get_gitlab_project.return_value["pathWithNamespace"] = "another/repo"
    with pytest.raises(AppError, match="路径已变化"):
        await service.rebind_frozen(
            repository=pin,
            binding=profile_binding(),
            project_id="p",
            user_id="another-user",
        )
    connections.get_gitlab_project.reset_mock()
    row = db.query(SoftwareRepository).filter_by(software_repository_id="repo-front").one()
    row.repository_project_id = "different-repository"
    db.flush()
    with pytest.raises(AppError):
        await service.rebind_frozen(
            repository=pin,
            binding=profile_binding(),
            project_id="p",
            user_id="another-user",
        )
    connections.get_gitlab_project.assert_not_awaited()


@pytest.fixture(autouse=True)
def ui_access(monkeypatch):
    from testing_agent.services import ui_generation_source as module

    monkeypatch.setattr(
        module,
        "resolve_repo_gitlab_access",
        AsyncMock(return_value=RepoGitlabAccess("ui-conn", "https://gitlab.example.com", "token")),
    )


def test_current_options_exposes_only_current_profile_and_safe_repositories():
    current = SimpleNamespace(
        candidate_id="profile-current",
        created_at=None,
        profile=repository_profile(
            profile_repository("repo-front", "frontend", confidence=0.7),
            profile_repository("repo-back", "backend", confidence=0.99),
        ),
        bindings=[profile_binding("repo-front", commit="sha-new"), profile_binding("repo-back")],
    )
    options = UiGenerationSourceService.current_options(current)
    assert options["currentProfile"]["candidateId"] == "profile-current"
    assert options["defaultRepositoryId"] == "repo-front"
    repo = options["currentProfile"]["repositories"][0]
    assert repo["isFrontend"] and repo["available"]
    assert repo["commit"] == "sha-new" and repo["branch"] == "main"
    assert "cloneUrl" not in repo and "connectionId" not in repo


def test_current_options_without_profile_is_empty():
    options = UiGenerationSourceService.current_options(None)
    assert options["currentProfile"] is None


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
    current = SimpleNamespace(
        profile=repository_profile(profile_repository("repo-front", "frontend")),
        bindings=[profile_binding()],
    )
    result = await service.check_current(
        current=current,
        project_id="p",
        user_id="u",
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
    session.add(AiGenerationStage(id="ui-surface", task_id=task.task_id, stage="ui_surface"))
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


async def test_source_options_and_check_handlers_return_safe_payloads(monkeypatch):
    from types import SimpleNamespace

    from testing_agent.handlers.generation_chain import (
        check_ui_generation_source,
        get_ui_generation_source_options,
    )
    from testing_agent.schemas.generation_chain import UiGenerationSourceCheckRequest
    from testing_agent.services.repository_profile_current import RepositoryProfileCurrent

    current = SimpleNamespace(
        candidate_id="profile-attempt-1", snapshot_id="snapshot", current_token="token"
    )
    monkeypatch.setattr(RepositoryProfileCurrent, "read", AsyncMock(return_value=current))

    options = {
        "currentProfile": {
            "candidateId": "profile-attempt-1",
            "label": "当前画像",
            "repositories": [
                {
                    "repositoryId": "repo-front",
                    "role": "frontend",
                    "isFrontend": True,
                    "available": True,
                }
            ],
            "defaultRepositoryId": "repo-front",
        },
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
        repository=SimpleNamespace(candidate_chain_task=AsyncMock(return_value=None)),
        tasks=SimpleNamespace(
            session=None,
            get_requirement=AsyncMock(return_value=SimpleNamespace(sprint_id="s")),
            get_sprint=AsyncMock(return_value=SimpleNamespace(project_id="p")),
        ),
        ui_sources=SimpleNamespace(
            current_options=lambda value: options if value is current else {},
            check_current=AsyncMock(return_value=checked),
        ),
    )
    listed = await get_ui_generation_source_options("r", user_id="u", service=service)
    data = listed["data"].model_dump(by_alias=True)
    assert data["currentProfile"]["candidateId"] == "profile-attempt-1"
    assert data["currentProfile"]["repositories"][0]["repositoryId"] == "repo-front"

    result = await check_ui_generation_source(
        "r",
        UiGenerationSourceCheckRequest(
            profileCandidateId="profile-attempt-1",
            repositoryId="repo-front",
            pinnedCommit="sha-old",
        ),
        user_id="u",
        service=service,
    )
    assert result["data"].model_dump(by_alias=True) == checked
    service.ui_sources.check_current.assert_awaited_once_with(
        current=current,
        project_id="p",
        user_id="u",
        repository_id="repo-front",
        pinned_commit="sha-old",
        gitlab_connection_id="",
    )


async def test_direct_attempt_view_hides_ui_repository_bindings(db):  # noqa: F811
    import json

    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.services.stage_storage.run_view import direct_attempt_view

    task = seed_ui_task(db)
    from testing_agent.models.generation_candidates import RequirementGenerationChain

    db.add(
        RequirementGenerationChain(
            chain_id="ui-chain", requirement_id=task.requirement_id, kind="ui", task_id=task.task_id
        )
    )
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
                "sourceProfileCandidateId": "profile-attempt-1",
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
