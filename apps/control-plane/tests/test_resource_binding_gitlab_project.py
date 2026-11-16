"""项目级资源绑定 API:禅道绑定生命周期与 GitLab 群组绑定移除。

覆盖:
- GitLab 群组绑定创建被明确拒绝;
- 项目级绑定共享读取与禅道绑定生命周期;
- 遗留 GitLab 绑定行不再支持更新，但仍可按通用规则删除。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient
from support.deletion import MemoryResourceDeletion

from testing_agent.api.deps import get_current_user_id, get_resource_binding_service
from testing_agent.app import create_app
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrForbidden,
    ErrNotFound,
    ErrRemoteResourceAlreadyBound,
)
from testing_agent.schemas.resource_binding import UpdateResourceBindingRequest
from testing_agent.services.resource_binding import ResourceBindingService
from testing_agent.services.service_instance import instance_key


def _request(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "provider": "zentao",
        "connectionId": "conn-1",
        "remoteResourceId": "101",
        "remoteNameSnapshot": "zentao-project",
    }
    body.update(overrides)
    return body


def _binding(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "binding_id": "binding-1",
        "instance_url": "https://zentao.example.com",
        "instance_key": instance_key("https://zentao.example.com"),
        "user_id": "user-1",
        "provider": "zentao",
        "connection_id": "conn-1",
        "local_resource_type": "project",
        "local_resource_id": "project-1",
        "remote_resource_type": "project",
        "remote_resource_id": "1",
        "remote_parent_id": "",
        "remote_name_snapshot": "禅道项目",
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
    def __init__(self) -> None:
        self.calls: list[tuple] = []

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
            connection_id=connection_id,
            base_url="https://zentao.example.com",
            access_token="token",
        )


class RecordingZentaoClient:
    session = AuthorizationDatabase()

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def get_project(self, connection, remote_resource_id):
        self.calls.append((connection, remote_resource_id))
        return SimpleNamespace(id=int(remote_resource_id), name="禅道项目", deleted=False)


class FakeMcpAccess:
    async def resolve(self, user_id, project_id, expected_instance=""):
        return SimpleNamespace(connection_id="conn-1", base_url="https://zentao.example.com")


class FakeRepository:
    session = AuthorizationDatabase()

    def __init__(self, owner: str = "user-1") -> None:
        self.project = SimpleNamespace(
            project_id="project-1",
            user_id=owner,
        )
        self.rows: list = []

    async def get_project(self, project_id):
        if self.project is None:
            return None
        return self.project if project_id == self.project.project_id else None

    async def get_sprint(self, sprint_id):
        return SimpleNamespace(sprint_id=sprint_id, project_id="project-1")

    async def get_requirement(self, requirement_id):
        return SimpleNamespace(requirement_id=requirement_id, sprint_id="sprint-1")

    async def get_active_by_local_resource(self, resource_type, resource_id):
        return None

    async def exists_active_by_remote_resource(self, *args, **kwargs):
        return False

    async def list(self, user_id, resource_type, resource_id):
        return [row for row in self.rows if row.user_id == user_id]

    async def list_project_bindings(self, user_id, project_id):
        return list(self.rows)

    async def get(self, resource_type, resource_id, binding_id):
        return next((row for row in self.rows if row.binding_id == binding_id), None)

    def add(self, binding) -> None:
        self.rows.append(binding)

    async def hard_delete(self, row):
        self.rows.remove(row)

    async def commit(self) -> None:
        pass

    async def refresh(self, row) -> None:
        pass


def _service(
    repository: FakeRepository,
    connections: RecordingConnectionService | None = None,
    zentao_client: RecordingZentaoClient | None = None,
) -> ResourceBindingService:
    return ResourceBindingService(
        repository,
        connections or RecordingConnectionService(),
        zentao_client if zentao_client is not None else RecordingZentaoClient(),
        zentao_access=FakeMcpAccess(),
        deletion=MemoryResourceDeletion(repository),
    )


@pytest.mark.asyncio
async def test_create_project_gitlab_group_binding_is_rejected():
    repository = FakeRepository()
    service = _service(repository)

    with pytest.raises(AppError) as exc_info:
        await service.create(
            "project",
            "project-1",
            _request(provider="gitlab", remoteResourceId="group-1"),
            "user-1",
        )

    assert exc_info.value.code == ErrBadRequest.code
    assert "项目级 GitLab 群组绑定已移除" in exc_info.value.message
    assert repository.rows == []


@pytest.mark.asyncio
async def test_create_missing_project_not_found():
    repository = FakeRepository()
    repository.project = None
    service = _service(repository)

    with pytest.raises(type(ErrNotFound)):
        await service.create("project", "project-1", _request(), "user-1")


@pytest.mark.asyncio
async def test_outsider_cannot_list_project_bindings():
    repository = FakeRepository()
    repository.rows.append(_binding())
    with pytest.raises(type(ErrForbidden)):
        await _service(repository).list("project", "project-1", "outsider")


@pytest.mark.asyncio
async def test_outsider_cannot_update_binding():
    repository = FakeRepository()
    repository.rows.append(_binding())
    with pytest.raises(type(ErrForbidden)):
        await _service(repository).update(
            "project", "project-1", "binding-1", {"remoteResourceId": "2"}, "outsider"
        )
    assert repository.rows[0].remote_resource_id == "1"


@pytest.mark.asyncio
async def test_update_missing_binding_not_found():
    repository = FakeRepository()
    service = _service(repository)

    with pytest.raises(type(ErrNotFound)):
        await service.update(
            "project", "project-1", "binding-1", {"remoteResourceId": "2"}, "user-1"
        )


@pytest.mark.asyncio
async def test_zentao_project_binding_can_be_reverified_by_owner():
    repository = FakeRepository()
    repository.rows.append(_binding())

    class Access:
        async def resolve(self, user_id, project_id, expected_instance=""):
            assert (user_id, project_id) == ("user-1", "project-1")
            return SimpleNamespace(connection_id="conn-2", base_url="https://zentao.example.com")

    service = _service(repository)
    service.zentao_access = Access()
    result = await service.update(
        "project", "project-1", "binding-1", {"connectionId": "conn-2"}, "user-1"
    )
    assert result["lastVerifiedAt"] is not None


@pytest.mark.asyncio
async def test_update_legacy_gitlab_requirement_binding_is_rejected():
    repository = FakeRepository()
    repository.rows.append(
        _binding(
            provider="gitlab",
            local_resource_type="requirement",
            local_resource_id="requirement-1",
            remote_resource_type="repository",
        )
    )
    service = _service(repository)

    with pytest.raises(AppError) as exc_info:
        await service.update(
            "requirement",
            "requirement-1",
            "binding-1",
            {"connectionId": "conn-2"},
            "user-1",
        )

    assert "项目级 GitLab 群组绑定已移除" in exc_info.value.message


@pytest.mark.asyncio
async def test_only_owner_can_delete_binding():
    repository = FakeRepository()
    repository.rows.append(_binding())
    service = _service(repository)
    with pytest.raises(type(ErrForbidden)):
        await service.delete("project", "project-1", "binding-1", "outsider")
    assert await service.delete("project", "project-1", "binding-1", "user-1") == {}


@pytest.mark.asyncio
async def test_delete_missing_binding_not_found():
    repository = FakeRepository()
    service = _service(repository)

    with pytest.raises(type(ErrNotFound)):
        await service.delete("project", "project-1", "binding-1", "user-1")


@pytest.mark.asyncio
async def test_owner_can_delete_zentao_binding_after_transfer():
    repository = FakeRepository()
    repository.rows.append(_binding(user_id="old-owner"))
    service = _service(repository)
    with pytest.raises(type(ErrForbidden)):
        await service.delete("project", "project-1", "binding-1", "old-owner")
    await service.delete("project", "project-1", "binding-1", "user-1")
    assert repository.rows == []


@pytest.mark.asyncio
async def test_zentao_binding_create_still_requires_owner():
    repository = FakeRepository()
    service = _service(repository)

    with pytest.raises(type(ErrForbidden)):
        await service.create("project", "project-1", _request(), "outsider")

    assert repository.rows == []


def test_update_request_schema_can_resolve_personal_connection_automatically():
    assert UpdateResourceBindingRequest().connection_id == ""


def test_project_binding_route_rejects_gitlab_group_binding():
    app = create_app()
    repository = FakeRepository(owner="user-1")
    service = _service(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_resource_binding_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        "/v1/projects/project-1/bindings",
        json={
            "provider": "gitlab",
            "connectionId": "conn-1",
            "remoteResourceId": "group-1",
        },
    )

    assert response.status_code == 400
    assert repository.rows == []


@pytest.mark.parametrize("duplicate", [True, False])
async def test_commit_collision_rolls_back_and_only_translates_binding_uniqueness(duplicate):
    from sqlalchemy.exc import IntegrityError

    class CollisionRepository(FakeRepository):
        rolled_back = False

        async def commit(self):
            key = "uq_binding_resource" if duplicate else "unrelated_constraint"
            raise IntegrityError("INSERT", {}, RuntimeError(f"Duplicate entry for key {key}"))

        async def rollback(self):
            self.rolled_back = True

    repository = CollisionRepository()
    with pytest.raises(AppError if duplicate else IntegrityError) as error:
        await _service(repository).create("project", "project-1", _request(), "user-1")
    assert repository.rolled_back
    if duplicate:
        assert error.value.code == ErrRemoteResourceAlreadyBound.code
