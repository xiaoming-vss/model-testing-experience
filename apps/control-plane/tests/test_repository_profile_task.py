"""Repository profile snapshot, result parsing and worker credential boundaries."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from testing_agent.core.errors import AppError
from testing_agent.services.repository_profile import (
    RepositoryProfileService,
    parse_repository_profile,
)


def make_task(**overrides) -> SimpleNamespace:
    fields = {
        "task_id": "task-1",
        "task_type": "repository_profile",
        "name": "登录改造 仓库画像",
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
        document_type="richtext",
        document_content="原始需求正文",
    )


def make_binding(
    binding_id: str,
    repository_id: str,
    group_id: str,
    *,
    branch: str = "develop",
    path: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        binding_id=binding_id,
        instance_url="https://gitlab.example.com",
        instance_key="gitlab-example",
        remote_resource_id=repository_id,
        remote_parent_id=group_id,
        remote_name_snapshot=path or f"team/{repository_id}",
        extra_json={"branch": branch},
    )


def make_connection(connection_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        connection_id=connection_id,
        provider="gitlab",
        project_id="project-1",
        base_url="https://gitlab.example.com",
        access_token=f"enc:{connection_id}",
    )


def understanding_version() -> SimpleNamespace:
    return SimpleNamespace(
        version_id="sv-understanding-1",
        version_no=1,
        task_id="understanding-task",
        attempt_id="understanding-attempt",
        stage="feature_understanding",
        artifact_content="已审核需求理解正文",
    )


class FakeCipher:
    def decrypt(self, value: str) -> str:
        return value.removeprefix("enc:")


class FakeTaskRepository:
    def __init__(self, requirement: SimpleNamespace | None = None):
        self.requirement = requirement or make_requirement()
        self.session = SimpleNamespace()

    async def get_requirement(self, requirement_id: str):
        return self.requirement


class FakeBindingRepository:
    def __init__(self, bindings: list, groups: dict[str, object] | None = None):
        self.bindings = bindings
        self.groups = groups or {}

    async def list_active_repo_bindings_for_requirement(self, requirement_id: str):
        return self.bindings

    async def get_active_project_group_binding(self, provider, project_id, group_id, instance=""):
        return self.groups.get(group_id)


class FakeIntegrationConnectionService:
    def __init__(self, connections: list, *, project_error: str = ""):
        self.connections = {item.connection_id: item for item in connections}
        self.project_error = project_error
        self.calls: list[dict] = []

    async def resolve_personal_connection(
        self, user_id, provider, project_id, instance_url, connection_id=""
    ):
        return next(item for item in self.connections.values() if item.base_url == instance_url)

    async def get_gitlab_project(self, connection_id, project_id, repository_id, *, user_id):
        if self.project_error:
            raise RuntimeError(self.project_error)
        self.calls.append(("project", repository_id))
        return {
            "id": repository_id,
            "pathWithNamespace": f"team/{repository_id}",
            "cloneUrl": f"https://gitlab.example.com/team/{repository_id}.git",
        }

    async def resolve_gitlab_commit(
        self, connection_id, project_id, repository_id, ref, *, user_id
    ):
        self.calls.append(("commit", repository_id, ref))
        return f"sha-{repository_id}-{ref}"


def make_service(
    *,
    bindings: list | None = None,
    groups: dict[str, object] | None = None,
    connections: list | None = None,
    project_error: str = "",
    requirement: SimpleNamespace | None = None,
) -> tuple[RepositoryProfileService, FakeIntegrationConnectionService]:
    integration = FakeIntegrationConnectionService(connections or [], project_error=project_error)
    service = RepositoryProfileService(
        FakeTaskRepository(requirement),
        FakeBindingRepository(bindings or [], groups),
        integration,
        FakeCipher(),
    )
    return service, integration


@pytest.fixture(autouse=True)
def approved_version(monkeypatch):
    from testing_agent.services import repository_profile as module

    version = understanding_version()
    requested: dict[str, str] = {}

    async def resolve(repository, requirement_id, version_id=""):
        requested["version_id"] = version_id
        return version

    monkeypatch.setattr(module, "approved_understanding", resolve)
    return version, requested


@pytest.mark.asyncio
async def test_snapshot_freezes_understanding_and_working_branch_head():
    service, integration = make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1")],
        groups={"group-1": SimpleNamespace(connection_id="conn-1")},
        connections=[make_connection("conn-1")],
    )

    snapshot = await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert snapshot["taskType"] == "repository_profile"
    assert snapshot["requirement"]["documentContent"] == "已审核需求理解正文"
    assert snapshot["requirementUnderstandingVersion"] == {
        "versionId": "sv-understanding-1",
        "versionNo": 1,
        "taskId": "understanding-task",
        "runId": "understanding-attempt",
    }
    assert snapshot["gitlabCredentialsUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/gitlab-credentials"
    )
    entry = snapshot["bindings"][0]
    assert entry["repositoryId"] == "repo-1"
    assert entry["pathWithNamespace"] == "team/repo-1"
    assert entry["branch"] == "develop"
    assert entry["cloneUrl"] == "https://gitlab.example.com/team/repo-1.git"
    assert entry["headCommit"] == "sha-repo-1-develop"
    assert entry["connectionId"] == "conn-1"
    assert entry["profileError"] == ""
    assert "baselineBranch" not in entry
    assert "baseCommit" not in entry
    assert [call for call in integration.calls if call[0] == "commit"] == [
        ("commit", "repo-1", "develop")
    ]


@pytest.mark.asyncio
async def test_explicit_understanding_version_is_forwarded(approved_version):
    _, requested = approved_version
    service, _ = make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1")],
        groups={"group-1": SimpleNamespace(connection_id="conn-1")},
        connections=[make_connection("conn-1")],
    )

    await service.build_snapshot(
        make_task(),
        "run-1",
        "worker-task-1",
        user_id="user-1",
        understanding_version_id="sv-old",
    )

    assert requested["version_id"] == "sv-old"


@pytest.mark.asyncio
async def test_no_binding_rejects_run():
    service, _ = make_service()

    with pytest.raises(AppError) as error:
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert "尚未绑定代码仓库" in str(error.value)


@pytest.mark.asyncio
async def test_missing_approved_understanding_rejects_run(monkeypatch):
    from testing_agent.services import repository_profile as module

    async def missing(repository, requirement_id, version_id=""):
        return None

    monkeypatch.setattr(module, "approved_understanding", missing)
    service, _ = make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1")],
        groups={"group-1": SimpleNamespace(connection_id="conn-1")},
        connections=[make_connection("conn-1")],
    )

    with pytest.raises(AppError) as error:
        await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert "先审核通过需求理解" in str(error.value)


@pytest.mark.asyncio
async def test_one_unreadable_repository_does_not_fail_the_others():
    service, _ = make_service(
        bindings=[
            make_binding("binding-1", "repo-1", "group-missing"),
            make_binding("binding-2", "repo-2", "group-1"),
        ],
        groups={"group-1": SimpleNamespace(connection_id="conn-1")},
        connections=[make_connection("conn-1")],
    )

    snapshot = await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    first, second = snapshot["bindings"]
    assert first["repositoryId"] == "repo-1"
    assert first["profileError"] == "未找到该仓库可用的 GitLab 个人授权"
    assert first["connectionId"] == ""
    assert first["cloneUrl"] == ""
    assert second["repositoryId"] == "repo-2"
    assert second["profileError"] == ""
    assert second["headCommit"] == "sha-repo-2-develop"


@pytest.mark.asyncio
async def test_missing_work_branch_marks_binding_unavailable():
    service, _ = make_service(
        bindings=[make_binding("binding-1", "repo-1", "group-1", branch="")],
        groups={"group-1": SimpleNamespace(connection_id="conn-1")},
        connections=[make_connection("conn-1")],
    )

    snapshot = await service.build_snapshot(make_task(), "run-1", "worker-task-1", user_id="user-1")

    assert snapshot["bindings"][0]["profileError"] == "仓库绑定缺少工作分支"


def test_parse_repository_profile_accepts_exact_contract_and_rejects_extras():
    valid = {
        "repositories": [
            {
                "repositoryId": "repo-1",
                "pathWithNamespace": "team/repo-1",
                "role": "backend",
                "responsibilitySummary": "提供登录接口",
                "techStack": ["Java"],
                "keyPaths": ["src"],
                "confidence": 0.8,
                "evidence": ["pom.xml"],
            }
        ],
        "overallSummary": "后端仓库",
    }
    parsed = parse_repository_profile(json.dumps(valid, ensure_ascii=False))
    assert parsed == valid

    with_extra = {**valid, "analyzedAt": "now"}
    assert parse_repository_profile(json.dumps(with_extra)) is None
    assert parse_repository_profile("{not json") is None


@pytest.mark.asyncio
async def test_credentials_payload_groups_only_resolved_profile_bindings():
    from testing_agent.services.code_risk_analysis import gitlab_credentials_payload

    connections = [
        SimpleNamespace(
            connection_id="conn-1",
            provider="gitlab",
            project_id="project-1",
            user_id="user-1",
            status="active",
            base_url="https://gitlab.example.com",
            access_token="enc:token",
        )
    ]
    session = SimpleNamespace()
    session.scalar = AsyncMock(return_value=connections[0])

    payload = await gitlab_credentials_payload(
        session,
        "task-1",
        "project-1",
        [
            {"repositoryId": "repo-1", "connectionId": "conn-1"},
            {"repositoryId": "repo-2", "connectionId": "", "profileError": "无权限"},
        ],
        FakeCipher(),
        user_id="user-1",
    )

    assert payload["credentials"] == [
        {
            "connectionId": "conn-1",
            "baseUrl": "https://gitlab.example.com",
            "accessToken": "token",
            "repositoryIds": ["repo-1"],
        }
    ]
