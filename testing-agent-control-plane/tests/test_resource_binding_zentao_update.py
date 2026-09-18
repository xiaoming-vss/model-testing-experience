"""禅道绑定更新使用本地父资源的绑定校验远端归属。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_resource_binding_providers import FakeRepository, RecordingConnectionService

from testing_agent.core.errors import ErrResourceBindingInvalid
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.services.resource_binding import ResourceBindingService
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_resource import ZentaoResourceClient


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_type", ["sprint", "requirement"])
@pytest.mark.parametrize(
    "scenario",
    [
        "empty_parent",
        "valid_parent",
        "missing_parent",
        "wrong_instance",
        "invalid_parent_id",
        "wrong_parent",
        "unavailable_resource",
        "deleted_resource",
        "later_page",
    ],
)
async def test_update_validates_parent_and_remote_membership(resource_type, scenario):
    repository = FakeRepository()
    binding = ResourceBinding(
        binding_id="binding-1",
        provider="zentao",
        connection_id="conn-1",
        instance_url="https://example.test",
        instance_key=instance_key("https://example.test"),
        local_resource_type=resource_type,
        local_resource_id="local-1",
        remote_resource_type="execution" if resource_type == "sprint" else "story",
        remote_resource_id="201",
        remote_parent_id="",
        status="active",
    )
    repository.get = AsyncMock(return_value=binding)
    repository.commit = AsyncMock()
    if scenario == "valid_parent":
        binding.remote_parent_id = "1"
    elif scenario == "wrong_parent":
        binding.remote_parent_id = "2"
    parent = await repository.get_active_by_local_resource("project", "project-1")
    if scenario == "missing_parent":
        parent = None
    elif scenario == "wrong_instance":
        parent.instance_key = instance_key("https://other.test")
    elif scenario == "invalid_parent_id":
        parent.remote_resource_id = ""
    repository.get_active_by_local_resource = AsyncMock(return_value=parent)
    connections = RecordingConnectionService()
    connections.resolve_personal_connection = AsyncMock(
        return_value=SimpleNamespace(connection_id="conn-1")
    )
    client = ZentaoResourceClient()
    client._list = AsyncMock(return_value={"items": [{"id": 201}], "total": 1})
    client._list_without_paging = AsyncMock(return_value={"items": [{"id": 201}], "total": 1})
    if scenario == "later_page":
        client._list.side_effect = [
            {"items": [{"id": value} for value in range(1, 101)], "total": 101},
            {"items": [{"id": 201}], "total": 101},
        ]
        client._list_without_paging.return_value = {
            "items": [{"id": value} for value in range(1, 202)],
            "total": 201,
        }
    elif scenario in {"unavailable_resource", "deleted_resource"}:
        response = {
            "items": [{"id": 201, "deleted": True}] if scenario == "deleted_resource" else [],
            "total": 0,
        }
        client._list.return_value = response
        client._list_without_paging.return_value = response
    service = ResourceBindingService(repository, connections, client)
    if scenario not in {"empty_parent", "valid_parent", "later_page"}:
        with pytest.raises(type(ErrResourceBindingInvalid)) as error:
            await service.update(
                resource_type, "local-1", "binding-1", {"connectionId": "conn-1"}, "user-1"
            )
        assert error.value.code == ErrResourceBindingInvalid.code
        repository.commit.assert_not_awaited()
        if scenario not in {"unavailable_resource", "deleted_resource"}:
            client._list.assert_not_awaited()
            client._list_without_paging.assert_not_awaited()
        return

    result = await service.update(
        resource_type, "local-1", "binding-1", {"connectionId": "conn-1"}, "user-1"
    )

    assert result["remoteParentId"] == "1"
    assert result["remoteResourceId"] == "201"
    fetch = client._list if resource_type == "sprint" else client._list_without_paging
    assert fetch.await_count == (2 if scenario == "later_page" and resource_type == "sprint" else 1)
    expected_path = (
        "api/v1/zentao/projects/1/executions"
        if resource_type == "sprint"
        else "api/v1/zentao/executions/1/stories"
    )
    assert fetch.call_args.args[1] == expected_path
