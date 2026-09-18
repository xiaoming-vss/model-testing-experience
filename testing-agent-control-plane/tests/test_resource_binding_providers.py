"""工单 01:资源绑定服务双提供商改造。

覆盖两个接缝:
- 请求 schema:provider 必填,显式取 zentao/gitlab 二选一;
- 服务层:按 provider 分发,gitlab 路径不触发禅道专属校验。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from pydantic import ValidationError

from testing_agent.core.errors import ErrBadRequest
from testing_agent.schemas.resource_binding import ResourceBindingRequest
from testing_agent.services.resource_binding import ResourceBindingService


def _request(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "provider": "zentao",
        "connectionId": "conn-1",
        "remoteResourceId": "101",
    }
    body.update(overrides)
    return body


class RecordingZentaoClient:
    session = AuthorizationDatabase()

    """gitlab 路径不得触碰禅道客户端;一旦被调用即留下记录。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def list_project_executions(self, connection, remote_id, **kwargs):
        return {"items": [{"id": 201}], "total": 1}

    async def get_project(self, connection, remote_resource_id):
        self.calls.append((connection, remote_resource_id))
        return SimpleNamespace(id=1, name="x", deleted=False)


class RecordingConnectionService:
    async def resolve_gitlab_group_id(self, connection_id, project_id, group_id, *, user_id):
        return group_id

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def resolve_zentao_access(self, user_id, connection_id, project_id=""):
        return SimpleNamespace(connection_id=connection_id, base_url="https://example.test")

    async def get_active_personal(self, user_id, provider, connection_id, project_id=""):
        self.calls.append((user_id, provider, connection_id, project_id))
        return SimpleNamespace(
            connection_id=connection_id, base_url="https://example.test", access_token="token"
        )


class FakeRepository:
    session = AuthorizationDatabase()

    def __init__(self) -> None:
        self.project = SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
        )
        self.rows: list = []

    async def get_project(self, project_id):
        return self.project

    async def get_sprint(self, sprint_id):
        return SimpleNamespace(sprint_id=sprint_id, project_id="project-1")

    async def get_requirement(self, requirement_id):
        return SimpleNamespace(requirement_id=requirement_id, sprint_id="sprint-1")

    async def get_active_by_local_resource(self, resource_type, resource_id):
        from testing_agent.services.service_instance import instance_key

        return SimpleNamespace(
            provider="zentao",
            remote_resource_id="1",
            instance_key=instance_key("https://example.test"),
        )

    async def exists_active_by_remote_resource(self, *args):
        return False

    async def get_active_project_group_binding(
        self, provider, project_id, group_id, *, for_update=False
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
        return False

    def add(self, binding) -> None:
        self.rows.append(binding)

    async def commit(self) -> None:
        pass

    async def refresh(self, row) -> None:
        pass


def test_request_schema_requires_explicit_provider():
    body = {k: v for k, v in _request().items() if k != "provider"}
    with pytest.raises(ValidationError):
        ResourceBindingRequest(**body)


def test_request_schema_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        ResourceBindingRequest(**_request(provider="github"))


def test_request_schema_accepts_gitlab_provider():
    request = ResourceBindingRequest(**_request(provider="gitlab"))
    assert request.provider == "gitlab"


@pytest.mark.asyncio
async def test_gitlab_project_binding_dispatches_without_touching_zentao_path():
    repository = FakeRepository()
    zentao_client = RecordingZentaoClient()
    connections = RecordingConnectionService()
    service = ResourceBindingService(repository, connections, zentao_client)

    result = await service.create(
        "project",
        "project-1",
        _request(provider="gitlab", remoteResourceId="group-1"),
        "user-1",
    )

    assert result["provider"] == "gitlab"
    assert result["remoteResourceType"] == "group"
    assert zentao_client.calls == []
    assert ("user-1", "gitlab", "conn-1", "project-1") in connections.calls
    assert repository.rows[0].provider == "gitlab"


@pytest.mark.asyncio
async def test_gitlab_sprint_binding_raises_placeholder():
    repository = FakeRepository()
    service = ResourceBindingService(
        repository, RecordingConnectionService(), RecordingZentaoClient()
    )

    with pytest.raises(type(ErrBadRequest)) as exc_info:
        await service.create(
            "sprint",
            "sprint-1",
            _request(provider="gitlab", remoteResourceId="group-1"),
            "user-1",
        )

    assert exc_info.value.code == ErrBadRequest.code
    assert repository.rows == []


@pytest.mark.asyncio
async def test_service_rejects_unknown_provider():
    repository = FakeRepository()
    service = ResourceBindingService(
        repository, RecordingConnectionService(), RecordingZentaoClient()
    )

    with pytest.raises(type(ErrBadRequest)) as exc_info:
        await service.create("project", "project-1", _request(provider="github"), "user-1")

    assert exc_info.value.code == ErrBadRequest.code


@pytest.mark.asyncio
async def test_sprint_zentao_binding_keeps_zentao_remote_type_default():
    repository = FakeRepository()
    service = ResourceBindingService(
        repository, RecordingConnectionService(), RecordingZentaoClient()
    )

    result = await service.create(
        "sprint",
        "sprint-1",
        _request(provider="zentao", remoteResourceId="201"),
        "user-1",
    )

    binding = repository.rows[0]
    assert binding.provider == "zentao"
    assert binding.remote_resource_type == "execution"
    assert result["remoteResourceType"] == "execution"


@pytest.mark.asyncio
@pytest.mark.parametrize("available", [True, False])
async def test_requirement_binding_uses_unpaged_story_client(monkeypatch, available):
    from unittest.mock import AsyncMock

    from testing_agent.core.errors import ErrResourceBindingInvalid
    from testing_agent.services.zentao_resource import ZentaoResourceClient

    repository = FakeRepository()
    client = ZentaoResourceClient()
    # Keep the real public method signature; replace only the network boundary.
    stories = [{"id": value} for value in range(1, 151)]
    if available:
        stories.append({"id": 201})
    fetch = AsyncMock(return_value={"items": stories, "total": len(stories)})
    monkeypatch.setattr(client, "_list_without_paging", fetch)
    service = ResourceBindingService(repository, RecordingConnectionService(), client)
    if available:
        result = await service.create(
            "requirement", "req-1", _request(remoteResourceId="201"), "user-1"
        )
        assert result["remoteResourceId"] == "201"
        assert result["remoteResourceType"] == "story"
    else:
        with pytest.raises(type(ErrResourceBindingInvalid)) as error:
            await service.create("requirement", "req-1", _request(remoteResourceId="201"), "user-1")
        assert error.value.code == ErrResourceBindingInvalid.code
        assert repository.rows == []
    fetch.assert_awaited_once()
    assert fetch.call_args.args[1] == "api/v1/zentao/executions/1/stories"
