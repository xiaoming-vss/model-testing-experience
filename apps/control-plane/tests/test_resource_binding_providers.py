"""工单 01:资源绑定服务双提供商改造。

覆盖两个接缝:
- 请求 schema:provider 必填,显式取 zentao/gitlab 二选一;
- 服务层:按 provider 分发,gitlab 路径不触发禅道专属校验。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from support.resource_binding_providers import (
    FakeMcpAccess as FakeMcpAccess,
)
from support.resource_binding_providers import (
    FakeRepository as FakeRepository,
)
from support.resource_binding_providers import (
    RecordingConnectionService as RecordingConnectionService,
)
from support.resource_binding_providers import (
    RecordingZentaoClient as RecordingZentaoClient,
)
from support.resource_binding_providers import (
    _request as _request,
)

from testing_agent.core.errors import ErrBadRequest
from testing_agent.schemas.resource_binding import ResourceBindingRequest
from testing_agent.services.resource_binding import ResourceBindingService


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
        repository,
        RecordingConnectionService(),
        RecordingZentaoClient(),
        zentao_access=FakeMcpAccess(),
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
        repository,
        RecordingConnectionService(),
        RecordingZentaoClient(),
        zentao_access=FakeMcpAccess(),
    )

    with pytest.raises(type(ErrBadRequest)) as exc_info:
        await service.create("project", "project-1", _request(provider="github"), "user-1")

    assert exc_info.value.code == ErrBadRequest.code


@pytest.mark.asyncio
async def test_sprint_zentao_binding_keeps_zentao_remote_type_default():
    repository = FakeRepository()
    service = ResourceBindingService(
        repository,
        RecordingConnectionService(),
        RecordingZentaoClient(),
        zentao_access=FakeMcpAccess(),
    )

    result = await service.create(
        "sprint",
        "local-1",
        _request(provider="zentao", remoteResourceId="201"),
        "user-1",
    )

    binding = repository.rows[0]
    assert binding.provider == "zentao"
    assert binding.remote_resource_type == "execution"
    assert result["remoteResourceType"] == "execution"


@pytest.mark.asyncio
@pytest.mark.parametrize("available", [True, False])
async def test_requirement_binding_uses_complete_story_list(available):
    from unittest.mock import AsyncMock

    from testing_agent.core.errors import ErrResourceBindingInvalid

    repository = FakeRepository()
    stories = [{"id": value} for value in range(1, 151)]
    if available:
        stories.append({"id": 201})
    fetch = AsyncMock(return_value={"items": stories, "total": len(stories)})
    client = SimpleNamespace(list_execution_stories=fetch)
    service = ResourceBindingService(
        repository, RecordingConnectionService(), client, zentao_access=FakeMcpAccess()
    )
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
    assert fetch.call_args.args[1] == "1"
    assert fetch.call_args.kwargs == {}
