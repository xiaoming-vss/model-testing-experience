"""工单 03:需求级 GitLab 仓库+分支绑定 API 与删除保护。

覆盖:
- 需求级绑定(仓库 + 分支)创建/查询/更新/删除,同一需求可绑多个仓库;
- 仓库不在项目已绑群组范围内(remote_parent_id 非激活群组绑定)时返回参数错误;
- 缺少 branch 返回参数错误,baseline_branch 可选;
- 绑定是项目级共享资产(ADR-0002):其他用户可见、可创建、可更新、可删除;
- 删除被需求绑定引用的群组绑定被阻止,返回受影响需求绑定清单(3506)。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from testing_agent.api.deps import get_current_user_id, get_resource_binding_service
from testing_agent.app import create_app
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrForbidden,
    ErrGroupBindingInUse,
    ErrNotFound,
    ErrRemoteResourceAlreadyBound,
    ErrResourceBindingInvalid,
)
from testing_agent.services.resource_binding import ResourceBindingService
from testing_agent.services.service_instance import instance_key


def _request(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "provider": "gitlab",
        "remoteResourceId": "repo-1",
        "remoteParentId": "group-1",
        "remoteNameSnapshot": "repo-one",
        "extraJson": {"branch": "main"},
    }
    body.update(overrides)
    return body


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
        "extra_json": {"branch": "main"},
        "created_at": None,
        "updated_at": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _group_binding(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "binding_id": "group-binding-1",
        "instance_url": "https://gitlab.example.com",
        "instance_key": instance_key("https://gitlab.example.com"),
        "user_id": "user-1",
        "provider": "gitlab",
        "connection_id": "conn-1",
        "local_resource_type": "project",
        "local_resource_id": "project-1",
        "remote_resource_type": "group",
        "remote_resource_id": "group-1",
        "remote_parent_id": "",
        "remote_name_snapshot": "group-one",
        "status": "active",
        "bound_at": None,
        "last_verified_at": None,
        "extra_json": {},
        "created_at": None,
        "updated_at": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class RecordingConnectionService:
    async def resolve_gitlab_group_id(self, connection_id, project_id, group_id, *, user_id):
        return group_id

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def ensure_gitlab_repository_scope(
        self, connection_id, project_id, group_id, repository_id, *, user_id
    ):
        self.calls.append((connection_id, project_id, group_id, repository_id))
        if repository_id == "outside-repo":
            raise ErrResourceBindingInvalid
        return repository_id

    async def resolve_personal_connection(
        self, user_id, provider, project_id, instance_url, connection_id=""
    ):
        return await self.get_active_personal(
            user_id, provider, connection_id or "conn-1", project_id
        )

    async def resolve_zentao_access(self, user_id, connection_id, project_id=""):
        return await self.get_active_personal(user_id, "zentao", connection_id, project_id)

    async def get_active_personal(self, user_id, provider, connection_id, project_id=""):
        self.calls.append((user_id, provider, connection_id, project_id))
        return SimpleNamespace(
            connection_id=connection_id, base_url="https://gitlab.example.com", access_token="token"
        )


class FakeRepository:
    session = AuthorizationDatabase()

    def __init__(self, bound_groups: set[str] | None = None) -> None:
        self.requirement = SimpleNamespace(requirement_id="req-1", sprint_id="sprint-1")
        self.bound_groups = {"group-1", "group-2"} if bound_groups is None else bound_groups
        self.rows: list = []
        self.affected: list = []

    async def get_project(self, project_id):
        return SimpleNamespace(project_id=project_id, user_id="user-1")

    async def get_sprint(self, sprint_id):
        return SimpleNamespace(sprint_id=sprint_id, project_id="project-1")

    async def get_requirement(self, requirement_id):
        if self.requirement is None:
            return None
        return self.requirement if requirement_id == self.requirement.requirement_id else None

    async def get_active_by_local_resource(self, resource_type, resource_id):
        return None

    async def exists_active_by_remote_resource(self, *args):
        return False

    async def get_active_project_group_binding(
        self, provider, project_id, group_id, *, for_update=False, instance=""
    ):
        existing = next(
            (
                r
                for r in self.rows
                if r.remote_resource_type == "group" and r.remote_resource_id == group_id
            ),
            None,
        )
        if existing is not None:
            return existing
        return (
            _group_binding(remote_resource_id=group_id) if group_id in self.bound_groups else None
        )

    async def exists_active_project_group_binding(
        self, provider, project_id, group_id, instance=""
    ):
        return group_id in self.bound_groups

    async def exists_active_requirement_repo_binding(
        self, requirement_id, repository_id, instance=""
    ):
        return any(
            row.provider == "gitlab"
            and row.local_resource_id == requirement_id
            and row.remote_resource_id == repository_id
            for row in self.rows
        )

    async def list(self, user_id, resource_type, resource_id):
        return [row for row in self.rows if row.user_id == user_id]

    async def list_project_bindings(self, user_id, project_id):
        return list(self.rows)

    async def list_requirement_bindings(self, user_id, requirement_id):
        return [
            row
            for row in self.rows
            if row.local_resource_id == requirement_id
            and (row.provider == "gitlab" or row.user_id == user_id)
        ]

    async def list_active_requirement_repo_bindings_for_group(
        self, project_id, group_id, instance=""
    ):
        return list(self.affected)

    async def get(self, resource_type, resource_id, binding_id):
        return next(
            (
                row
                for row in self.rows
                if row.binding_id == binding_id and row.local_resource_id == resource_id
            ),
            None,
        )

    def add(self, binding) -> None:
        self.rows.append(binding)

    async def hard_delete(self, row):
        self.rows.remove(row)

    async def commit(self) -> None:
        pass

    async def refresh(self, row) -> None:
        pass


def _service(repository: FakeRepository) -> ResourceBindingService:
    return ResourceBindingService(repository, RecordingConnectionService())


@pytest.mark.asyncio
async def test_create_requirement_gitlab_repo_binding():
    repository = FakeRepository()
    service = _service(repository)

    result = await service.create("requirement", "req-1", _request(), "user-1")

    binding = repository.rows[0]
    assert result["bindingId"] == binding.binding_id
    assert result["provider"] == "gitlab"
    assert result["connectionId"] == ""
    assert result["localResourceType"] == "requirement"
    assert result["localResourceId"] == "req-1"
    assert result["remoteResourceType"] == "repository"
    assert result["remoteResourceId"] == "repo-1"
    assert result["remoteParentId"] == "group-1"
    assert result["branch"] == "main"
    assert result["baselineBranch"] == ""
    assert binding.user_id == "user-1"
    assert binding.extra_json == {"branch": "main"}


@pytest.mark.asyncio
async def test_create_with_baseline_branch_is_optional_but_stored():
    repository = FakeRepository()
    service = _service(repository)

    result = await service.create(
        "requirement",
        "req-1",
        _request(extraJson={"branch": "main", "baseline_branch": "release/1.0"}),
        "user-1",
    )

    assert result["baselineBranch"] == "release/1.0"
    assert repository.rows[0].extra_json == {
        "branch": "main",
        "baseline_branch": "release/1.0",
    }


@pytest.mark.asyncio
async def test_create_repo_outside_bound_groups_rejected():
    repository = FakeRepository()
    service = _service(repository)

    with pytest.raises(type(ErrResourceBindingInvalid)) as exc_info:
        await service.create("requirement", "req-1", _request(remoteParentId="group-9"), "user-1")

    assert exc_info.value.code == ErrResourceBindingInvalid.code
    assert repository.rows == []


@pytest.mark.asyncio
async def test_create_with_no_bound_groups_rejected():
    repository = FakeRepository(bound_groups=set())
    service = _service(repository)

    with pytest.raises(type(ErrResourceBindingInvalid)):
        await service.create("requirement", "req-1", _request(), "user-1")

    assert repository.rows == []


@pytest.mark.asyncio
async def test_create_missing_branch_rejected():
    repository = FakeRepository()
    service = _service(repository)

    for extra in ({}, {"branch": ""}, {"branch": "  "}):
        with pytest.raises(type(ErrResourceBindingInvalid)) as exc_info:
            await service.create("requirement", "req-1", _request(extraJson=extra), "user-1")
        assert exc_info.value.code == ErrResourceBindingInvalid.code

    assert repository.rows == []


@pytest.mark.asyncio
async def test_create_missing_repo_or_group_rejected():
    repository = FakeRepository()
    service = _service(repository)

    for body in (_request(remoteResourceId=""), _request(remoteParentId="")):
        with pytest.raises(type(ErrBadRequest)) as exc_info:
            await service.create("requirement", "req-1", body, "user-1")
        assert exc_info.value.code == ErrBadRequest.code

    assert repository.rows == []


@pytest.mark.asyncio
async def test_create_missing_requirement_not_found():
    repository = FakeRepository()
    repository.requirement = None
    service = _service(repository)

    with pytest.raises(type(ErrNotFound)):
        await service.create("requirement", "req-1", _request(), "user-1")


@pytest.mark.asyncio
async def test_duplicate_repo_binding_rejected():
    repository = FakeRepository()
    repository.rows.append(_binding())
    service = _service(repository)

    with pytest.raises(type(ErrRemoteResourceAlreadyBound)) as exc_info:
        await service.create("requirement", "req-1", _request(), "user-1")

    assert exc_info.value.code == ErrRemoteResourceAlreadyBound.code
    assert len(repository.rows) == 1


@pytest.mark.asyncio
async def test_same_requirement_can_bind_multiple_repositories():
    repository = FakeRepository()
    service = _service(repository)

    await service.create("requirement", "req-1", _request(), "user-1")
    await service.create(
        "requirement",
        "req-1",
        _request(remoteResourceId="repo-2", remoteParentId="group-2", extraJson={"branch": "dev"}),
        "user-1",
    )

    assert len(repository.rows) == 2
    assert {row.remote_resource_id for row in repository.rows} == {"repo-1", "repo-2"}


@pytest.mark.asyncio
async def test_outsider_cannot_create_requirement_binding():
    repository = FakeRepository()
    with pytest.raises(type(ErrForbidden)):
        await _service(repository).create("requirement", "req-1", _request(), "outsider")
    assert repository.rows == []


@pytest.mark.asyncio
async def test_gitlab_sprint_binding_still_rejected():
    repository = FakeRepository()
    service = _service(repository)

    with pytest.raises(type(ErrBadRequest)) as exc_info:
        await service.create("sprint", "sprint-1", _request(), "user-1")

    assert exc_info.value.code == ErrBadRequest.code
    assert repository.rows == []


@pytest.mark.asyncio
async def test_list_requirement_bindings_shared_visibility():
    repository = FakeRepository()
    repository.rows.append(_binding())
    repository.rows.append(
        _binding(
            binding_id="zentao-1",
            provider="zentao",
            user_id="user-1",
            remote_resource_type="story",
            extra_json={},
        )
    )
    service = _service(repository)

    result = await service.list("requirement", "req-1", "user-1")

    assert result["total"] == 2
    assert result["items"][0]["bindingId"] == "binding-1"
    assert result["items"][0]["branch"] == "main"


@pytest.mark.asyncio
async def test_list_missing_requirement_not_found():
    repository = FakeRepository()
    repository.requirement = None
    service = _service(repository)

    with pytest.raises(type(ErrNotFound)):
        await service.list("requirement", "req-1", "user-1")


@pytest.mark.asyncio
async def test_update_branch_and_baseline_branch():
    repository = FakeRepository()
    binding = _binding()
    repository.rows.append(binding)
    service = _service(repository)

    result = await service.update(
        "requirement",
        "req-1",
        "binding-1",
        {"branch": "dev", "baselineBranch": "release/1.0"},
        "user-1",
    )

    assert result["branch"] == "dev"
    assert result["baselineBranch"] == "release/1.0"
    assert binding.extra_json == {"branch": "dev", "baseline_branch": "release/1.0"}


@pytest.mark.asyncio
async def test_update_can_clear_baseline_branch():
    repository = FakeRepository()
    binding = _binding(extra_json={"branch": "main", "baseline_branch": "release/1.0"})
    repository.rows.append(binding)
    service = _service(repository)

    result = await service.update(
        "requirement", "req-1", "binding-1", {"baselineBranch": ""}, "user-1"
    )

    assert result["baselineBranch"] == ""
    assert binding.extra_json == {"branch": "main"}


@pytest.mark.asyncio
async def test_update_missing_branch_rejected():
    repository = FakeRepository()
    repository.rows.append(_binding())
    service = _service(repository)

    with pytest.raises(type(ErrResourceBindingInvalid)):
        await service.update("requirement", "req-1", "binding-1", {"branch": "  "}, "user-1")


@pytest.mark.asyncio
async def test_update_omitted_fields_are_untouched():
    repository = FakeRepository()
    binding = _binding(extra_json={"branch": "main", "baseline_branch": "release/1.0"})
    repository.rows.append(binding)
    service = _service(repository)

    result = await service.update("requirement", "req-1", "binding-1", {"branch": "dev"}, "user-1")

    assert result["branch"] == "dev"
    assert result["baselineBranch"] == "release/1.0"
    assert binding.remote_parent_id == "group-1"
    assert binding.remote_name_snapshot == "repo-one"


@pytest.mark.asyncio
async def test_update_missing_binding_not_found():
    repository = FakeRepository()
    service = _service(repository)

    with pytest.raises(type(ErrNotFound)):
        await service.update("requirement", "req-1", "binding-1", {"branch": "dev"}, "user-1")


@pytest.mark.asyncio
async def test_zentao_binding_update_requires_owner():
    repository = FakeRepository()
    repository.rows.append(_binding(provider="zentao", extra_json={}))
    with pytest.raises(type(ErrForbidden)):
        await _service(repository).update("requirement", "req-1", "binding-1", {}, "outsider")


@pytest.mark.asyncio
async def test_any_user_can_delete_requirement_binding():
    repository = FakeRepository()
    binding = _binding()
    repository.rows.append(binding)
    service = _service(repository)

    result = await service.delete("requirement", "req-1", "binding-1", "user-1")

    assert result == {}
    assert binding.status == "unbound"
    assert binding not in repository.rows


@pytest.mark.asyncio
async def test_delete_group_binding_blocked_when_referenced_by_requirement_bindings():
    repository = FakeRepository()
    group_binding = _group_binding()
    affected = _binding(extra_json={"branch": "main", "baseline_branch": "release/1.0"})
    repository.rows.append(group_binding)
    repository.affected.append(affected)
    service = _service(repository)

    with pytest.raises(AppError) as exc_info:
        await service.delete("project", "project-1", "group-binding-1", "user-1")

    error = exc_info.value
    assert error.code == ErrGroupBindingInUse.code
    assert error.data == {
        "bindings": [
            {
                "bindingId": "binding-1",
                "instanceUrl": "https://gitlab.example.com",
                "provider": "gitlab",
                "connectionId": "",
                "localResourceType": "requirement",
                "localResourceId": "req-1",
                "remoteResourceType": "repository",
                "remoteResourceId": "repo-1",
                "remoteParentId": "group-1",
                "remoteNameSnapshot": "repo-one",
                "status": "active",
                "boundAt": None,
                "lastVerifiedAt": None,
                "branch": "main",
                "baselineBranch": "release/1.0",
                "createdAt": None,
                "updatedAt": None,
            }
        ]
    }
    assert group_binding.status == "active"
    assert group_binding in repository.rows


@pytest.mark.asyncio
async def test_delete_group_binding_succeeds_when_not_referenced():
    repository = FakeRepository()
    group_binding = _group_binding()
    repository.rows.append(group_binding)
    service = _service(repository)

    result = await service.delete("project", "project-1", "group-binding-1", "user-1")

    assert result == {}
    assert group_binding.status == "unbound"


def test_requirement_binding_routes_serve_full_lifecycle():
    app = create_app()
    repository = FakeRepository()
    service = _service(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_resource_binding_service] = lambda: service
    client = TestClient(app)

    created = client.post(
        "/v1/requirements/req-1/bindings",
        json={
            "provider": "gitlab",
            "remoteResourceId": "repo-1",
            "remoteParentId": "group-1",
            "extraJson": {"branch": "main"},
        },
    )
    assert created.status_code == 200
    data = created.json()["data"]
    binding_id = data["bindingId"]
    assert data["branch"] == "main"
    assert data["connectionId"] == ""

    listed = client.get("/v1/requirements/req-1/bindings")
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1

    patched = client.patch(
        f"/v1/requirements/req-1/bindings/{binding_id}",
        json={"branch": "dev", "baselineBranch": "release/1.0"},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["branch"] == "dev"
    assert patched.json()["data"]["baselineBranch"] == "release/1.0"

    deleted = client.delete(f"/v1/requirements/req-1/bindings/{binding_id}")
    assert deleted.status_code == 200
    assert repository.rows == []


def test_patch_partial_update_does_not_clear_omitted_fields():
    app = create_app()
    repository = FakeRepository()
    service = _service(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_resource_binding_service] = lambda: service
    client = TestClient(app)

    created = client.post(
        "/v1/requirements/req-1/bindings",
        json={
            "provider": "gitlab",
            "remoteResourceId": "repo-1",
            "remoteParentId": "group-1",
            "extraJson": {"branch": "main", "baselineBranch": "release/1.0"},
        },
    )
    binding_id = created.json()["data"]["bindingId"]

    patched = client.patch(
        f"/v1/requirements/req-1/bindings/{binding_id}",
        json={"branch": "dev"},
    )

    assert patched.status_code == 200
    data = patched.json()["data"]
    assert data["branch"] == "dev"
    assert data["baselineBranch"] == "release/1.0"
    assert data["remoteNameSnapshot"] == ""
    assert repository.rows[0].remote_name_snapshot == ""


def test_group_binding_delete_route_returns_affected_bindings_when_blocked():
    app = create_app()
    repository = FakeRepository()
    repository.rows.append(_group_binding())
    repository.affected.append(_binding())
    service = _service(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_resource_binding_service] = lambda: service
    client = TestClient(app)

    response = client.delete("/v1/projects/project-1/bindings/group-binding-1")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == ErrGroupBindingInUse.code
    assert body["data"]["bindings"][0]["bindingId"] == "binding-1"
    assert body["data"]["bindings"][0]["branch"] == "main"


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_group_bound_but_repository_outside_is_rejected(operation):
    repository = FakeRepository()
    service = _service(repository)
    if operation == "create":
        call = service.create(
            "requirement", "req-1", _request(remoteResourceId="outside-repo"), "user-1"
        )
    else:
        repository.rows.append(_binding(remote_resource_id="outside-repo"))
        call = service.update("requirement", "req-1", "binding-1", {"branch": "new"}, "user-1")
    with pytest.raises(AppError) as error:
        await call
    assert error.value.code == ErrResourceBindingInvalid.code
    assert (
        not repository.rows
        if operation == "create"
        else repository.rows[0].extra_json["branch"] == "main"
    )


async def test_repository_alias_cannot_bypass_uniqueness():
    class CanonicalConnections(RecordingConnectionService):
        async def ensure_gitlab_repository_scope(
            self, connection_id, project_id, group_id, repository_id, *, user_id
        ):
            assert repository_id in {"11", "team/sub/repo"}
            return "11"

    repository = FakeRepository()
    service = ResourceBindingService(repository, CanonicalConnections())
    first = await service.create(
        "requirement", "req-1", _request(remoteResourceId="team/sub/repo"), "user-1"
    )
    assert first["remoteResourceId"] == "11"
    with pytest.raises(AppError) as error:
        await service.create("requirement", "req-1", _request(remoteResourceId="11"), "user-1")
    assert error.value.code == ErrRemoteResourceAlreadyBound.code
    assert len(repository.rows) == 1
