"""工单 02:项目级 GitLab 群组绑定 API。

覆盖:
- 项目级群组绑定创建/查询/接管/删除;
- 同一群组重复绑定被拒绝;
- 绑定是项目级共享资产(ADR-0002):查询不过滤 user_id,其他用户可见并可接管;
- 禅道绑定行为回归:创建仍要求项目所有者,删除仍要求所有者与创建者。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient
from pydantic import ValidationError

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
        "provider": "gitlab",
        "connectionId": "conn-1",
        "remoteResourceId": "group-1",
        "remoteNameSnapshot": "group-one",
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


class RecordingZentaoClient:
    session = AuthorizationDatabase()

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def get_project(self, connection, remote_resource_id):
        self.calls.append((connection, remote_resource_id))
        return SimpleNamespace(id=int(remote_resource_id), name="禅道项目", deleted=False)


class FakeRepository:
    session = AuthorizationDatabase()

    def __init__(self, owner: str = "user-1") -> None:
        self.project = SimpleNamespace(
            project_id="project-1",
            user_id=owner,
        )
        self.rows: list = []
        self.group_already_bound = False
        self.list_calls: list[tuple] = []

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

    async def exists_active_by_remote_resource(self, *args):
        return False

    async def get_active_project_group_binding(
        self, provider, project_id, group_id, *, for_update=False, instance=""
    ):
        return next(
            (
                r
                for r in self.rows
                if r.remote_resource_type == "group" and r.remote_resource_id == group_id
            ),
            None,
        )

    async def exists_active_project_group_binding(
        self, provider, project_id, group_id, instance=""
    ):
        return self.group_already_bound

    async def exists_active_requirement_repo_binding(
        self, requirement_id, repository_id, instance=""
    ):
        return False

    async def list_requirement_bindings(self, user_id, requirement_id):
        return [
            row
            for row in self.rows
            if row.local_resource_type == "requirement"
            and row.local_resource_id == requirement_id
            and row.user_id == user_id
        ]

    async def list_active_requirement_repo_bindings_for_group(
        self, project_id, group_id, instance=""
    ):
        return []

    async def list(self, user_id, resource_type, resource_id):
        return [row for row in self.rows if row.user_id == user_id]

    async def list_project_bindings(self, user_id, project_id):
        self.list_calls.append((user_id, project_id))
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
    )


@pytest.mark.asyncio
async def test_create_project_gitlab_group_binding():
    repository = FakeRepository()
    connections = RecordingConnectionService()
    zentao_client = RecordingZentaoClient()
    service = _service(repository, connections, zentao_client)

    result = await service.create("project", "project-1", _request(), "user-1")

    binding = repository.rows[0]
    assert result["bindingId"] == binding.binding_id
    assert result["provider"] == "gitlab"
    assert result["connectionId"] == "conn-1"
    assert result["localResourceType"] == "project"
    assert result["localResourceId"] == "project-1"
    assert result["remoteResourceType"] == "group"
    assert result["remoteResourceId"] == "group-1"
    assert result["remoteParentId"] == ""
    assert result["remoteNameSnapshot"] == "group-one"
    assert binding.user_id == "user-1"
    assert connections.calls == [("user-1", "gitlab", "conn-1", "project-1")]
    assert zentao_client.calls == []


@pytest.mark.asyncio
async def test_create_requires_group_id_and_connection_id():
    repository = FakeRepository()
    service = _service(repository)

    for body in (_request(remoteResourceId=""), _request(connectionId="")):
        with pytest.raises(type(ErrBadRequest)) as exc_info:
            await service.create("project", "project-1", body, "user-1")
        assert exc_info.value.code == ErrBadRequest.code

    assert repository.rows == []


@pytest.mark.asyncio
async def test_create_missing_project_not_found():
    repository = FakeRepository()
    repository.project = None
    service = _service(repository)

    with pytest.raises(type(ErrNotFound)):
        await service.create("project", "project-1", _request(), "user-1")


@pytest.mark.asyncio
async def test_duplicate_group_binding_rejected():
    repository = FakeRepository()
    repository.group_already_bound = True
    service = _service(repository)

    with pytest.raises(type(ErrRemoteResourceAlreadyBound)) as exc_info:
        await service.create("project", "project-1", _request(), "user-1")

    assert exc_info.value.code == ErrRemoteResourceAlreadyBound.code
    assert repository.rows == []


@pytest.mark.asyncio
async def test_outsider_cannot_list_project_bindings():
    repository = FakeRepository()
    repository.rows.append(_binding())
    with pytest.raises(type(ErrForbidden)):
        await _service(repository).list("project", "project-1", "outsider")


@pytest.mark.asyncio
async def test_outsider_cannot_reverify_binding():
    repository = FakeRepository()
    repository.rows.append(_binding())
    with pytest.raises(type(ErrForbidden)):
        await _service(repository).update(
            "project", "project-1", "binding-1", {"connectionId": "conn-2"}, "outsider"
        )
    assert repository.rows[0].connection_id == "conn-1"


@pytest.mark.asyncio
async def test_update_requires_connection_id():
    repository = FakeRepository()
    repository.rows.append(_binding())
    service = _service(repository)

    with pytest.raises(type(ErrBadRequest)):
        await service.update("project", "project-1", "binding-1", {}, "user-1")


@pytest.mark.asyncio
async def test_update_missing_binding_not_found():
    repository = FakeRepository()
    service = _service(repository)

    with pytest.raises(type(ErrNotFound)):
        await service.update(
            "project", "project-1", "binding-1", {"connectionId": "conn-2"}, "user-1"
        )


@pytest.mark.asyncio
async def test_zentao_project_binding_can_be_reverified_by_owner():
    repository = FakeRepository()
    repository.rows.append(_binding(provider="zentao", remote_resource_id="1"))
    result = await _service(repository).update(
        "project", "project-1", "binding-1", {"connectionId": "conn-2"}, "user-1"
    )
    assert result["lastVerifiedAt"] is not None


@pytest.mark.asyncio
async def test_update_non_group_gitlab_binding_rejected():
    repository = FakeRepository()
    repository.rows.append(_binding(remote_resource_type="repository"))
    service = _service(repository)

    with pytest.raises(type(ErrBadRequest)):
        await service.update(
            "project", "project-1", "binding-1", {"connectionId": "conn-2"}, "user-1"
        )


@pytest.mark.asyncio
async def test_only_owner_can_delete_gitlab_group_binding():
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
    repository.rows.append(_binding(provider="zentao", user_id="old-owner"))
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
        await service.create(
            "project",
            "project-1",
            {"provider": "zentao", "connectionId": "conn-1", "remoteResourceId": "101"},
            "outsider",
        )

    assert repository.rows == []


def test_update_request_schema_requires_connection_id():
    with pytest.raises(ValidationError):
        UpdateResourceBindingRequest(**{})


def test_patch_project_binding_route_reverifies_without_transferring_connection():
    app = create_app()
    repository = FakeRepository(owner="user-1")
    repository.rows.append(_binding())
    service = _service(repository, RecordingConnectionService())
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_resource_binding_service] = lambda: service
    client = TestClient(app)

    response = client.patch(
        "/v1/projects/project-1/bindings/binding-1",
        json={"connectionId": "conn-2"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["connectionId"] == "conn-1"


def test_project_binding_routes_serve_full_lifecycle():
    app = create_app()
    repository = FakeRepository(owner="user-1")
    service = _service(repository, RecordingConnectionService())
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_resource_binding_service] = lambda: service
    client = TestClient(app)

    created = client.post(
        "/v1/projects/project-1/bindings",
        json={
            "provider": "gitlab",
            "connectionId": "conn-1",
            "remoteResourceId": "group-1",
        },
    )
    assert created.status_code == 200
    binding_id = created.json()["data"]["bindingId"]

    listed = client.get("/v1/projects/project-1/bindings")
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["items"][0]["bindingId"] == binding_id

    deleted = client.delete(f"/v1/projects/project-1/bindings/{binding_id}")
    assert deleted.status_code == 200
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


async def test_group_alias_cannot_bypass_uniqueness():
    class CanonicalConnections(RecordingConnectionService):
        async def resolve_gitlab_group_id(self, connection_id, project_id, group_id, *, user_id):
            assert group_id in {"7", "team/sub"}
            return "7"

    class Repository(FakeRepository):
        async def exists_active_project_group_binding(
            self, provider, project_id, group_id, instance=""
        ):
            return any(row.remote_resource_id == group_id for row in self.rows)

    repository = Repository()
    service = _service(repository, CanonicalConnections())
    first = await service.create(
        "project", "project-1", _request(remoteResourceId="team/sub"), "user-1"
    )
    assert first["remoteResourceId"] == "7"
    with pytest.raises(AppError) as error:
        await service.create("project", "project-1", _request(remoteResourceId="7"), "user-1")
    assert error.value.code == ErrRemoteResourceAlreadyBound.code
    assert len(repository.rows) == 1
