"""Validate server-reported namespaces, including subgroup and prefix boundaries."""

import httpx
import pytest

from testing_agent.services.gitlab_resource import GitLabResourceClient, GitLabResourceError


@pytest.mark.parametrize(
    ("namespace", "kind", "allowed"),
    [
        ("team", "group", True),
        ("team/sub/deep", "group", True),
        ("team-other", "group", False),
        ("outside", "group", False),
        ("team", "user", False),
        ("", "group", False),
    ],
)
async def test_repository_scope_uses_remote_namespace(namespace, kind, allowed):
    def respond(request):
        assert request.headers["PRIVATE-TOKEN"] == "test-token"
        if request.url.path == "/api/v4/groups/7":
            return httpx.Response(200, json={"id": 7, "full_path": "team"})
        assert request.url.path == "/api/v4/projects/11"
        return httpx.Response(
            200,
            json={
                "id": 11,
                "namespace": {
                    "full_path": namespace,
                    "kind": kind,
                },
            },
        )

    client = GitLabResourceClient(httpx.MockTransport(respond))
    result = await client.get_repository_group_scope(
        "https://gitlab.example", "test-token", "7", "11"
    )
    assert result["withinGroup"] is allowed


async def test_inaccessible_repository_does_not_pass_validation():
    client = GitLabResourceClient(httpx.MockTransport(lambda _: httpx.Response(403)))
    with pytest.raises(GitLabResourceError):
        await client.get_repository_group_scope("https://gitlab.example", "token", "7", "11")


@pytest.mark.parametrize("identifier", ["7", "team/sub"])
async def test_connection_service_returns_canonical_group_and_repository_ids(identifier):
    from test_gitlab_resource_proxy import (
        FakeCipher,
        FakeIntegrationConnectionRepository,
        connection_row,
    )

    from testing_agent.services.integration_connection import IntegrationConnectionService

    def respond(request):
        if "/groups/" in request.url.path:
            return httpx.Response(200, json={"id": 7, "full_path": "team/sub"})
        return httpx.Response(
            200, json={"id": 11, "namespace": {"full_path": "team/sub/nested", "kind": "group"}}
        )

    service = IntegrationConnectionService(
        FakeIntegrationConnectionRepository([connection_row()]),
        credential_cipher=FakeCipher(),
        gitlab_resource_client=GitLabResourceClient(httpx.MockTransport(respond)),
    )
    assert (
        await service.resolve_gitlab_group_id("conn-1", "project-1", identifier, user_id="user-1")
        == "7"
    )
    assert (
        await service.ensure_gitlab_repository_scope(
            "conn-1", "project-1", "7", "team/sub/nested/repo", user_id="user-1"
        )
        == "11"
    )
