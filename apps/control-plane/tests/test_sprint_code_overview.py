"""工单 08:迭代代码变更概览端点(RC-6)。

覆盖:
- 概览聚合与去重(同仓库同分支去重、同仓库多分支独立对比单元);
- 变更量口径与基线规则一致:手工/自动基线作 compare from,无基线仓库以
  git 空树 SHA 对比并标记「新增仓库」;
- 短缓存(窗口内重复请求不重复调 GitLab)与绑定变更后的主动失效;
- 无任何绑定时返回空态结构;
- 单仓库失败(compare 失败、凭据缺失、基线解析失败)仅标注该仓库错误与
  补救建议,其余仓库与整体返回不受影响;
- 绑定创建/接管/更新/删除触发缓存失效回调(禅道绑定不触发);
- /v1 端点鉴权与分发。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from testing_agent.api.deps import (
    get_current_user_id,
    get_sprint_code_overview_service,
)
from testing_agent.app import create_app
from testing_agent.core.config import get_settings
from testing_agent.core.errors import AppError, ErrNotFound
from testing_agent.services.baseline_resolution import BindingResolution
from testing_agent.services.gitlab_resource import GitLabResourceError
from testing_agent.services.service_instance import instance_key
from testing_agent.services.sprint_code_overview import (
    COMPARE_ERROR_REMEDIATION,
    CONNECTION_UNRESOLVED_ERROR,
    CONNECTION_UNRESOLVED_REMEDIATION,
    EMPTY_TREE_SHA,
    RESOLUTION_ERROR_REMEDIATION,
    SprintCodeOverviewService,
)

NOW = datetime(2026, 8, 20, 10, 30)


def _sprint(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "sprint_id": "sprint-1",
        "project_id": "project-1",
        "name": "迭代一",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _binding(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "binding_id": "binding-1",
        "instance_url": "https://gitlab.example.com",
        "instance_key": instance_key("https://gitlab.example.com"),
        "user_id": "user-1",
        "provider": "gitlab",
        "connection_id": "",
        "local_resource_type": "requirement",
        "local_resource_id": "req-1",
        "remote_resource_type": "repository",
        "remote_resource_id": "repo-1",
        "remote_parent_id": "group-1",
        "remote_name_snapshot": "repo-one",
        "status": "active",
        "bound_at": None,
        "last_verified_at": None,
        "extra_json": {"branch": "develop"},
        "created_at": NOW,
        "updated_at": None,
        "id": 1,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _resolution(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "repository_id": "repo-1",
        "branch": "develop",
        "baseline_ref": "release-1.0",
        "note": "",
        "error": "",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _row(binding: SimpleNamespace, resolution: SimpleNamespace) -> BindingResolution:
    return BindingResolution(binding, resolution)


def _connection(connection_id: str = "conn-1", base_url: str = "https://gitlab.example.com"):
    return SimpleNamespace(
        connection_id=connection_id,
        base_url=base_url,
        access_token="enc:token-1",
    )


class FakeCipher:
    def __init__(self, tokens: dict[str, str] | None = None) -> None:
        self.tokens = tokens or {}

    def decrypt(self, value: str) -> str:
        if value not in self.tokens:
            raise ValueError("bad ciphertext")
        return self.tokens[value]


class FakeSprintService:
    def __init__(self, sprint: SimpleNamespace | None = None, error: AppError | None = None):
        self.sprint = sprint if sprint is not None else _sprint()
        self.error = error
        self.calls: list[tuple[str, str]] = []

    async def get_accessible_entity(self, user_id: str, sprint_id: str):
        self.calls.append((user_id, sprint_id))
        if self.error is not None:
            raise self.error
        return self.sprint


class FakeBaselineResolutionService:
    def __init__(self, rows: list[BindingResolution] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[str] = []

    async def resolve_for_sprint(self, sprint_id: str):
        self.calls.append(sprint_id)
        return list(self.rows)


class FakeBindingRepository:
    def __init__(self, group_bindings: dict[str, SimpleNamespace] | None = None) -> None:
        self.group_bindings = group_bindings or {}
        self.calls: list[tuple[str, str, str]] = []

    async def get_active_project_group_binding(
        self, provider, project_id, group_id, *, for_update=False, instance=""
    ):
        self.calls.append((provider, project_id, group_id))
        return self.group_bindings.get(group_id)


class FakeGitlabClient:
    def __init__(
        self,
        results: dict[str, dict] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.results = results or {}
        self.errors = errors or {}
        self.calls: list[dict] = []

    async def compare_repository_branches(
        self, base_url, access_token, repository_id, *, from_ref=None, to_ref=None
    ):
        self.calls.append(
            {
                "base_url": base_url,
                "token": access_token,
                "repository_id": repository_id,
                "from": from_ref,
                "to": to_ref,
            }
        )
        if repository_id in self.errors:
            raise self.errors[repository_id]
        default = {"commitsCount": 0, "additions": 0, "deletions": 0}
        return dict(self.results.get(repository_id, default))


class FakeIntegrationConnectionService:
    def __init__(self, connections: list | None = None, client: FakeGitlabClient | None = None):
        self.connections = {c.connection_id: c for c in connections or []}
        self.gitlab_resource_client = client or FakeGitlabClient()

    async def resolve_personal_connection(
        self, user_id, provider, project_id, instance_url, connection_id=""
    ):
        assert user_id == "user-1"
        rows = [
            c
            for c in self.connections.values()
            if c.base_url == instance_url
            and (not connection_id or c.connection_id == connection_id)
        ]
        if len(rows) != 1:
            raise ErrNotFound
        return rows[0]


def make_service(
    *,
    sprint: SimpleNamespace | None = None,
    sprint_service: FakeSprintService | None = None,
    rows: list[BindingResolution] | None = None,
    group_bindings: dict[str, SimpleNamespace] | None = None,
    connections: list | None = None,
    tokens: dict[str, str] | None = None,
    client: FakeGitlabClient | None = None,
) -> tuple[
    SprintCodeOverviewService,
    FakeSprintService,
    FakeBaselineResolutionService,
    FakeGitlabClient,
]:
    sprint_service = sprint_service or FakeSprintService(sprint)
    baseline = FakeBaselineResolutionService(rows)
    client = client or FakeGitlabClient()
    if group_bindings is None:
        group_bindings = {"group-1": SimpleNamespace(connection_id="conn-1")}
    if connections is None:
        connections = [_connection()]
    if tokens is None:
        tokens = {"enc:token-1": "plain-token-1"}
    service = SprintCodeOverviewService(
        sprint_service,
        FakeBindingRepository(group_bindings),
        baseline,
        FakeIntegrationConnectionService(connections, client=client),
        FakeCipher(tokens),
    )
    return service, sprint_service, baseline, client


# ---------------------------------------------------------------------------
# 聚合与基线口径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_aggregates_and_dedupes_same_repo_branch():
    first = _binding(binding_id="binding-1", id=1, created_at=NOW)
    dup = _binding(
        binding_id="binding-2",
        id=2,
        local_resource_id="req-2",
        created_at=datetime(2026, 8, 20, 11, 0),
    )
    second = _binding(
        binding_id="binding-3",
        id=3,
        remote_resource_id="repo-2",
        remote_parent_id="group-1",
        remote_name_snapshot="repo-two",
    )
    client = FakeGitlabClient(
        {
            "repo-1": {"commitsCount": 4, "additions": 120, "deletions": 8},
            "repo-2": {"commitsCount": 1, "additions": 10, "deletions": 2},
        }
    )
    service, _, baseline, _ = make_service(
        rows=[
            _row(dup, _resolution()),
            _row(first, _resolution()),
            _row(second, _resolution(repository_id="repo-2")),
        ],
        connections=[_connection()],
        tokens={"enc:token-1": "plain-token-1"},
        client=client,
    )

    overview = await service.get_overview("user-1", "sprint-1")

    assert overview["sprintId"] == "sprint-1"
    assert overview["projectId"] == "project-1"
    assert overview["generatedAt"]
    assert len(overview["repositories"]) == 2
    entry = overview["repositories"][0]
    assert entry["repositoryId"] == "repo-1"
    assert entry["name"] == "repo-one"
    assert entry["groupId"] == "group-1"
    assert entry["branch"] == "develop"
    assert entry["baselineRef"] == "release-1.0"
    assert entry["isNewRepository"] is False
    assert entry["commitsCount"] == 4
    assert entry["additions"] == 120
    assert entry["deletions"] == 8
    assert entry["error"] == ""
    assert entry["remediation"] == ""
    assert baseline.calls == ["sprint-1"]
    assert overview["repositories"][1]["repositoryId"] == "repo-2"


@pytest.mark.asyncio
async def test_same_repo_different_branches_keep_separate_entries():
    develop = _binding(binding_id="b-1", id=1, extra_json={"branch": "develop"})
    release = _binding(binding_id="b-2", id=2, extra_json={"branch": "release-1.0"})
    client = FakeGitlabClient(
        {
            "repo-1": {"commitsCount": 1, "additions": 2, "deletions": 3},
        }
    )
    service, _, _, _ = make_service(
        rows=[
            _row(release, _resolution(branch="release-1.0")),
            _row(develop, _resolution(branch="develop")),
        ],
        connections=[_connection()],
        tokens={"enc:token-1": "plain-token-1"},
        client=client,
    )

    overview = await service.get_overview("user-1", "sprint-1")

    assert [row["branch"] for row in overview["repositories"]] == ["release-1.0", "develop"]
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_no_baseline_compared_against_empty_tree_and_marked_new():
    service, _, _, client = make_service(
        rows=[_row(_binding(), _resolution(baseline_ref=None))],
        connections=[_connection()],
        tokens={"enc:token-1": "plain-token-1"},
    )

    overview = await service.get_overview("user-1", "sprint-1")

    entry = overview["repositories"][0]
    assert entry["isNewRepository"] is True
    assert entry["baselineRef"] is None
    assert entry["error"] == ""
    assert client.calls == [
        {
            "base_url": "https://gitlab.example.com",
            "token": "plain-token-1",
            "repository_id": "repo-1",
            "from": EMPTY_TREE_SHA,
            "to": "develop",
        }
    ]


@pytest.mark.asyncio
async def test_manual_baseline_used_as_compare_from():
    service, _, _, client = make_service(
        rows=[_row(_binding(), _resolution(baseline_ref="main"))],
        connections=[_connection()],
        tokens={"enc:token-1": "plain-token-1"},
    )

    await service.get_overview("user-1", "sprint-1")

    assert client.calls[0]["from"] == "main"
    assert client.calls[0]["to"] == "develop"


@pytest.mark.asyncio
async def test_no_bindings_returns_empty_state():
    service, _, baseline, client = make_service(rows=[])

    overview = await service.get_overview("user-1", "sprint-1")

    assert overview == {
        "sprintId": "sprint-1",
        "projectId": "project-1",
        "generatedAt": overview["generatedAt"],
        "repositories": [],
    }
    assert baseline.calls == ["sprint-1"]
    assert client.calls == []


@pytest.mark.asyncio
async def test_sprint_ownership_enforced():
    service, _, _, _ = make_service(sprint_service=FakeSprintService(error=ErrNotFound))

    with pytest.raises(AppError) as exc_info:
        await service.get_overview("user-1", "sprint-1")
    assert exc_info.value.code == ErrNotFound.code


# ---------------------------------------------------------------------------
# 单仓库失败降级
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_failure_marks_only_that_repo():
    broken = _binding(
        binding_id="b-1",
        id=1,
        remote_resource_id="repo-1",
        remote_parent_id="group-1",
    )
    healthy = _binding(
        binding_id="b-2",
        id=2,
        remote_resource_id="repo-2",
        remote_parent_id="group-1",
        remote_name_snapshot="repo-two",
    )
    client = FakeGitlabClient(
        {"repo-2": {"commitsCount": 2, "additions": 5, "deletions": 1}},
        errors={"repo-1": GitLabResourceError("GitLab 资源查询失败，HTTP 404: not found", 404)},
    )
    service, _, _, _ = make_service(
        rows=[
            _row(broken, _resolution()),
            _row(healthy, _resolution(repository_id="repo-2")),
        ],
        connections=[_connection()],
        tokens={"enc:token-1": "plain-token-1"},
        client=client,
    )

    overview = await service.get_overview("user-1", "sprint-1")

    broken_entry = overview["repositories"][0]
    assert broken_entry["error"]
    assert "404" in broken_entry["error"]
    assert broken_entry["remediation"] == COMPARE_ERROR_REMEDIATION
    assert broken_entry["commitsCount"] == 0
    assert broken_entry["additions"] == 0
    assert broken_entry["deletions"] == 0
    healthy_entry = overview["repositories"][1]
    assert healthy_entry["error"] == ""
    assert healthy_entry["commitsCount"] == 2
    assert healthy_entry["additions"] == 5


@pytest.mark.asyncio
async def test_connection_unresolved_marks_error_with_remediation():
    service, _, _, client = make_service(
        rows=[_row(_binding(), _resolution())],
        group_bindings={},
        connections=[],
    )

    overview = await service.get_overview("user-1", "sprint-1")

    entry = overview["repositories"][0]
    assert entry["error"] == CONNECTION_UNRESOLVED_ERROR
    assert entry["remediation"] == CONNECTION_UNRESOLVED_REMEDIATION
    assert entry["commitsCount"] == 0
    assert client.calls == []


@pytest.mark.asyncio
async def test_baseline_resolution_error_skips_compare():
    service, _, _, client = make_service(
        rows=[
            _row(
                _binding(),
                _resolution(baseline_ref=None, error="基线分支 main 已不存在,请手工指定基线分支"),
            )
        ],
        connections=[_connection()],
        tokens={"enc:token-1": "plain-token-1"},
    )

    overview = await service.get_overview("user-1", "sprint-1")

    entry = overview["repositories"][0]
    assert "基线分支" in entry["error"]
    assert entry["remediation"] == RESOLUTION_ERROR_REMEDIATION
    assert entry["isNewRepository"] is False
    assert client.calls == []


@pytest.mark.asyncio
async def test_each_overview_request_checks_personal_remote_access():
    service, _, baseline, client = make_service(rows=[_row(_binding(), _resolution())])
    await service.get_overview("user-1", "sprint-1")
    await service.get_overview("user-1", "sprint-1")
    assert baseline.calls == ["sprint-1", "sprint-1"]
    assert len(client.calls) == 2


def worker_settings():
    return get_settings()


class FakeOverviewEndpointService:
    async def get_overview(self, user_id, sprint_id, connection_ids=None):
        assert user_id == "user-1"
        assert sprint_id == "sprint-1"
        return {
            "sprintId": "sprint-1",
            "projectId": "project-1",
            "generatedAt": "2026-08-21T10:30:00+00:00",
            "repositories": [
                {
                    "repositoryId": "repo-1",
                    "name": "repo-one",
                    "groupId": "group-1",
                    "branch": "develop",
                    "baselineRef": None,
                    "baselineNote": "",
                    "isNewRepository": True,
                    "commitsCount": 3,
                    "additions": 20,
                    "deletions": 1,
                    "error": "",
                    "remediation": "",
                }
            ],
        }


def test_code_overview_endpoint_dispatch_and_shape():
    app = create_app(worker_settings())
    app.dependency_overrides[get_sprint_code_overview_service] = lambda: (
        FakeOverviewEndpointService()
    )
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    client = TestClient(app)

    response = client.get("/v1/sprints/sprint-1/code-overview")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["sprintId"] == "sprint-1"
    assert body["data"]["repositories"][0]["repositoryId"] == "repo-1"


def test_code_overview_endpoint_requires_auth():
    app = create_app(worker_settings())
    app.dependency_overrides[get_sprint_code_overview_service] = lambda: (
        FakeOverviewEndpointService()
    )
    client = TestClient(app)

    response = client.get("/v1/sprints/sprint-1/code-overview")

    assert response.status_code == 401


def test_code_overview_openapi_tag_and_path():
    app = create_app(worker_settings())
    paths = app.openapi()["paths"]

    assert "/v1/sprints/{sprintId}/code-overview" in paths
    assert paths["/v1/sprints/{sprintId}/code-overview"]["get"]["tags"] == ["Sprint Metrics"]
