from types import SimpleNamespace

import httpx
import pytest
from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from testing_agent.api.deps import get_current_user_id, get_integration_connection_service
from testing_agent.app import create_app
from testing_agent.core.errors import AppError, ErrNotFound
from testing_agent.services.gitlab_resource import GitLabResourceClient, GitLabResourceError
from testing_agent.services.integration_connection import IntegrationConnectionService

GROUPS_URL = "/v1/projects/project-1/integrations/gitlab/connections/conn-1/groups"
REPOSITORIES_URL = (
    "/v1/projects/project-1/integrations/gitlab/connections/conn-1/groups/team/repositories"
)
BRANCHES_URL = (
    "/v1/projects/project-1/integrations/gitlab/connections/conn-1/repositories/team%2Fapi/branches"
)


def connection_row(project_id="project-1", user_id="user-1", connection_id="conn-1"):
    return SimpleNamespace(
        connection_id=connection_id,
        provider="gitlab",
        project_id=project_id,
        user_id=user_id,
        base_url="https://gitlab.example.com",
        access_token="enc:glpat-secret-token",
        status="active",
    )


class FakeIntegrationConnectionRepository:
    session = AuthorizationDatabase()

    async def get_project(self, project_id):
        return SimpleNamespace(project_id=project_id, user_id="user-1")

    def __init__(self, rows=None):
        self.rows = list(rows or [])

    async def get(self, user_id, provider, connection_id, project_id=""):
        return next(
            (
                row
                for row in self.rows
                if row.user_id == user_id
                and row.provider == provider
                and row.connection_id == connection_id
                and row.project_id == project_id

            ),
            None,
        )


class FakeCipher:
    def encrypt(self, plaintext):
        return f"enc:{plaintext}"

    def decrypt(self, ciphertext):
        return ciphertext.removeprefix("enc:")


class FakeGitLabResourceClient:
    def __init__(self):
        self.calls = []
        self.results = {}

    async def list_groups(self, base_url, access_token, *, search="", page=1, page_size=100):
        self.calls.append(("groups", base_url, access_token, search, page, page_size))
        return self._resolve("groups")

    async def list_group_repositories(
        self, base_url, access_token, group_id, *, page=1, page_size=100
    ):
        self.calls.append(("repositories", base_url, access_token, group_id, page, page_size))
        return self._resolve("repositories")

    async def list_repository_branches(
        self, base_url, access_token, repository_id, *, search="", page=1, page_size=100
    ):
        self.calls.append(
            ("branches", base_url, access_token, repository_id, search, page, page_size)
        )
        return self._resolve("branches")

    def _resolve(self, key):
        value = self.results.get(key)
        if isinstance(value, Exception):
            raise value
        if value is None:
            return {"items": [], "total": 0}
        return value


def proxy_client(repository, resource_client):
    app = create_app()
    service = IntegrationConnectionService(
        repository,
        gitlab_resource_client=resource_client,
        credential_cipher=FakeCipher(),
    )
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_integration_connection_service] = lambda: service
    return TestClient(app)


@pytest.mark.asyncio
async def test_client_lists_groups_with_subgroups_search_and_pagination():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {"id": 1, "name": "team", "full_path": "team", "parent_id": None},
                {"id": 2, "name": "infra", "full_path": "team/infra", "parent_id": 1},
            ],
            headers={"X-Total": "7"},
        )

    client = GitLabResourceClient(transport=httpx.MockTransport(respond))

    result = await client.list_groups(
        "https://gitlab.example.com",
        "glpat-secret-token",
        search="infra",
        page=2,
        page_size=50,
    )

    assert str(requests[0].url) == (
        "https://gitlab.example.com/api/v4/groups"
        "?top_level_only=false&order_by=name&sort=asc&page=2&per_page=50&search=infra"
    )
    assert requests[0].headers["PRIVATE-TOKEN"] == "glpat-secret-token"
    assert result["total"] == 7
    assert result["items"] == [
        {
            "id": 1,
            "name": "team",
            "fullPath": "team",
            "parentId": None,
            "description": "",
            "webUrl": "",
        },
        {
            "id": 2,
            "name": "infra",
            "fullPath": "team/infra",
            "parentId": 1,
            "description": "",
            "webUrl": "",
        },
    ]


@pytest.mark.asyncio
async def test_client_lists_group_repositories_including_subgroups_with_encoded_path():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "id": 11,
                    "name": "api",
                    "path": "api",
                    "path_with_namespace": "team/api",
                    "namespace": {"full_path": "team"},
                    "default_branch": "main",
                }
            ],
        )

    client = GitLabResourceClient(transport=httpx.MockTransport(respond))

    result = await client.list_group_repositories(
        "https://gitlab.example.com",
        "glpat-secret-token",
        "team/infra",
        page=1,
        page_size=100,
    )

    assert str(requests[0].url) == (
        "https://gitlab.example.com/api/v4/groups/team%2Finfra/projects"
        "?include_subgroups=true&with_shared=false&page=1&per_page=100"
    )
    assert result["total"] == 1
    assert result["items"][0]["pathWithNamespace"] == "team/api"
    assert result["items"][0]["namespaceFullPath"] == "team"


@pytest.mark.asyncio
async def test_client_lists_repository_branches_with_search_and_encoded_path():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "name": "main",
                    "default": True,
                    "protected": True,
                    "commit": {"id": "abc123", "title": "init"},
                }
            ],
        )

    client = GitLabResourceClient(transport=httpx.MockTransport(respond))

    result = await client.list_repository_branches(
        "https://gitlab.example.com",
        "glpat-secret-token",
        "team/api",
        search="main",
        page=2,
        page_size=50,
    )

    assert str(requests[0].url) == (
        "https://gitlab.example.com/api/v4/projects/team%2Fapi/repository/branches"
        "?page=2&per_page=50&search=main"
    )
    assert result["items"] == [
        {
            "name": "main",
            "isDefault": True,
            "isProtected": True,
            "commitId": "abc123",
            "commitTitle": "init",
        }
    ]


@pytest.mark.asyncio
async def test_client_total_falls_back_to_item_count_without_total_header():
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1, "name": "g", "full_path": "g"}])

    client = GitLabResourceClient(transport=httpx.MockTransport(respond))

    result = await client.list_groups("https://gitlab.example.com", "glpat-secret-token")

    assert result["total"] == 1


@pytest.mark.asyncio
async def test_client_raises_with_status_code_on_gitlab_errors():
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "401 Unauthorized"})

    client = GitLabResourceClient(transport=httpx.MockTransport(respond))

    with pytest.raises(GitLabResourceError) as exc_info:
        await client.list_groups("https://gitlab.example.com", "glpat-secret-token")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_client_raises_on_network_error_without_status_code():
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = GitLabResourceClient(transport=httpx.MockTransport(respond))

    with pytest.raises(GitLabResourceError) as exc_info:
        await client.list_groups("https://gitlab.example.com", "glpat-secret-token")

    assert exc_info.value.status_code == 0


@pytest.mark.asyncio
async def test_service_lists_groups_with_personal_connection_and_decrypted_token():
    repository = FakeIntegrationConnectionRepository([connection_row()])
    resource_client = FakeGitLabResourceClient()
    resource_client.results["groups"] = {
        "items": [{"id": 1, "name": "team"}],
        "total": 1,
    }
    service = IntegrationConnectionService(
        repository,
        gitlab_resource_client=resource_client,
        credential_cipher=FakeCipher(),
    )

    result = await service.list_gitlab_groups(
        "conn-1", project_id="project-1", search="team", page=2, page_size=25, user_id="user-1"
    )

    assert resource_client.calls == [
        ("groups", "https://gitlab.example.com", "glpat-secret-token", "team", 2, 25)
    ]
    assert result["connectionId"] == "conn-1"
    assert result["items"] == [{"id": 1, "name": "team"}]


@pytest.mark.asyncio
async def test_service_lists_group_repositories_and_branches_with_context_ids():
    repository = FakeIntegrationConnectionRepository([connection_row()])
    resource_client = FakeGitLabResourceClient()
    service = IntegrationConnectionService(
        repository,
        gitlab_resource_client=resource_client,
        credential_cipher=FakeCipher(),
    )

    repositories = await service.list_gitlab_group_repositories(
        "conn-1", "team", project_id="project-1", user_id="user-1"
    )
    branches = await service.list_gitlab_repository_branches(
        "conn-1",
        "team/api",
        project_id="project-1",
        search="main",
        page=2,
        page_size=25,
        user_id="user-1",
    )

    assert repositories == {
        "connectionId": "conn-1",
        "groupId": "team",
        "items": [],
        "total": 0,
    }
    assert branches == {
        "connectionId": "conn-1",
        "repositoryId": "team/api",
        "items": [],
        "total": 0,
    }
    assert resource_client.calls[0][:4] == (
        "repositories",
        "https://gitlab.example.com",
        "glpat-secret-token",
        "team",
    )
    assert resource_client.calls[1] == (
        "branches",
        "https://gitlab.example.com",
        "glpat-secret-token",
        "team/api",
        "main",
        2,
        25,
    )


@pytest.mark.asyncio
async def test_service_maps_gitlab_401_to_auth_failed_error_code():
    repository = FakeIntegrationConnectionRepository([connection_row()])
    resource_client = FakeGitLabResourceClient()
    resource_client.results["groups"] = GitLabResourceError(
        "GitLab 资源查询失败，HTTP 401", status_code=401
    )
    service = IntegrationConnectionService(
        repository,
        gitlab_resource_client=resource_client,
        credential_cipher=FakeCipher(),
    )

    with pytest.raises(AppError) as exc_info:
        await service.list_gitlab_groups("conn-1", project_id="project-1", user_id="user-1")

    assert exc_info.value.code == 3403


@pytest.mark.asyncio
async def test_service_maps_other_gitlab_errors_to_resource_unavailable_error_code():
    repository = FakeIntegrationConnectionRepository([connection_row()])
    resource_client = FakeGitLabResourceClient()
    resource_client.results["groups"] = GitLabResourceError(
        "GitLab 资源查询失败，HTTP 500", status_code=500
    )
    service = IntegrationConnectionService(
        repository,
        gitlab_resource_client=resource_client,
        credential_cipher=FakeCipher(),
    )

    with pytest.raises(AppError) as exc_info:
        await service.list_gitlab_groups("conn-1", project_id="project-1", user_id="user-1")

    assert exc_info.value.code == 3405


@pytest.mark.asyncio
async def test_service_rejects_connection_missing_or_not_in_project():
    repository = FakeIntegrationConnectionRepository(
        [connection_row(), connection_row(project_id="project-2", connection_id="conn-2")]
    )
    service = IntegrationConnectionService(
        repository,
        gitlab_resource_client=FakeGitLabResourceClient(),
        credential_cipher=FakeCipher(),
    )

    with pytest.raises(AppError) as exc_info:
        await service.list_gitlab_groups("conn-missing", project_id="project-1", user_id="user-1")
    assert exc_info.value.code == ErrNotFound.code

    with pytest.raises(AppError) as exc_info:
        await service.list_gitlab_groups("conn-2", project_id="project-1", user_id="user-1")
    assert exc_info.value.code == ErrNotFound.code


def test_groups_endpoint_returns_normalized_payload():
    repository = FakeIntegrationConnectionRepository([connection_row()])
    resource_client = FakeGitLabResourceClient()
    resource_client.results["groups"] = {
        "items": [{"id": 1, "name": "team", "fullPath": "team"}],
        "total": 1,
    }
    client = proxy_client(repository, resource_client)

    response = client.get(GROUPS_URL, params={"search": "team", "page": 1, "pageSize": 100})

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["connectionId"] == "conn-1"
    assert body["data"]["total"] == 1
    assert body["data"]["items"] == [{"id": 1, "name": "team", "fullPath": "team"}]
    assert resource_client.calls[0][0] == "groups"


def test_repositories_and_branches_endpoints_return_context_ids():
    repository = FakeIntegrationConnectionRepository([connection_row()])
    resource_client = FakeGitLabResourceClient()
    client = proxy_client(repository, resource_client)

    repositories = client.get(REPOSITORIES_URL, params={"page": 1, "pageSize": 100})
    branches = client.get(BRANCHES_URL, params={"search": "main", "page": 2, "pageSize": 25})

    assert repositories.status_code == 200
    assert repositories.json()["data"]["groupId"] == "team"
    assert resource_client.calls[0][:4] == (
        "repositories",
        "https://gitlab.example.com",
        "glpat-secret-token",
        "team",
    )
    assert branches.status_code == 200
    assert branches.json()["data"]["repositoryId"] == "team/api"
    assert resource_client.calls[1] == (
        "branches",
        "https://gitlab.example.com",
        "glpat-secret-token",
        "team/api",
        "main",
        2,
        25,
    )


def test_endpoints_return_structured_error_codes_instead_of_500():
    repository = FakeIntegrationConnectionRepository([connection_row()])
    resource_client = FakeGitLabResourceClient()
    resource_client.results["groups"] = GitLabResourceError(
        "GitLab 资源查询失败，HTTP 401", status_code=401
    )
    client = proxy_client(repository, resource_client)

    response = client.get(GROUPS_URL)

    assert response.status_code == 400
    assert response.json()["code"] == 3403

    resource_client.results["groups"] = GitLabResourceError(
        "GitLab 资源查询失败，HTTP 500", status_code=500
    )

    response = client.get(GROUPS_URL)

    assert response.status_code == 400
    assert response.json()["code"] == 3405


def test_endpoints_reject_connection_not_in_project():
    repository = FakeIntegrationConnectionRepository(
        [connection_row(project_id="project-2", connection_id="conn-2")]
    )
    client = proxy_client(repository, FakeGitLabResourceClient())

    response = client.get("/v1/projects/project-1/integrations/gitlab/connections/conn-2/groups")

    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_endpoints_require_authentication():
    repository = FakeIntegrationConnectionRepository([connection_row()])
    resource_client = FakeGitLabResourceClient()
    app = create_app()
    service = IntegrationConnectionService(
        repository,
        gitlab_resource_client=resource_client,
        credential_cipher=FakeCipher(),
    )
    app.dependency_overrides[get_integration_connection_service] = lambda: service
    client = TestClient(app)

    response = client.get(GROUPS_URL)

    assert response.status_code == 401


def test_proxy_routes_follow_go_contract_path_conversion():
    paths = create_app().openapi()["paths"]

    assert "/v1/projects/{projectId}/integrations/gitlab/connections/{connectionId}/groups" in paths
    repositories_path = (
        "/v1/projects/{projectId}/integrations/gitlab/connections/{connectionId}"
        "/groups/{groupId}/repositories"
    )
    assert repositories_path in paths
    param_names = {param["name"] for param in paths[repositories_path]["get"]["parameters"]}
    assert "groupId" in param_names
    assert "group_id" not in param_names
    assert (
        "/v1/projects/{projectId}/integrations/gitlab/connections/{connectionId}"
        "/repositories/{repositoryId}/branches" in paths
    )


@pytest.mark.asyncio
async def test_client_raises_on_invalid_base_url_as_resource_error():
    client = GitLabResourceClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))

    with pytest.raises(GitLabResourceError) as exc_info:
        await client.list_groups("not-a-url", "glpat-secret-token")

    assert exc_info.value.status_code == 0


# ---------------------------------------------------------------------------
# 工单 08:compare API(迭代代码概览统计)
# ---------------------------------------------------------------------------

COMPARE_RESPONSE = {
    "commit": {"id": "abc123"},
    "commits": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}],
    "diffs": [
        {
            "old_path": "src/auth.py",
            "new_path": "src/auth.py",
            "diff": (
                "@@ -1,3 +1,4 @@\n"
                " import os\n"
                "+import jwt\n"
                "-old_token = os.getenv('TOKEN')\n"
                "+token = os.getenv('TOKEN')\n"
                "+    \n"
            ),
        },
        {
            "old_path": "README.md",
            "new_path": "README.md",
            "diff": "@@ -1,1 +1,1 @@\n-old\n+new\n",
        },
        {"old_path": "renamed.py", "new_path": "moved.py", "diff": ""},
    ],
}


def test_diff_line_stats_counts_additions_and_deletions():
    from testing_agent.services.gitlab_resource import diff_line_stats

    assert diff_line_stats("@@ -1,2 +1,3 @@\n+a\n+b\n-c\n") == (2, 1)
    assert diff_line_stats("") == (0, 0)
    # 文件头行(+++/---)不计入。
    assert diff_line_stats("+++ b/src/auth.py\n--- a/src/auth.py\n+x\n-y\n") == (1, 1)


def test_compare_payload_computes_stats_from_diffs():
    from testing_agent.services.gitlab_resource import compare_payload

    assert compare_payload(COMPARE_RESPONSE) == {
        "commitsCount": 3,
        "additions": 4,
        "deletions": 2,
    }
    assert compare_payload({"commits": None, "diffs": None}) == {
        "commitsCount": 0,
        "additions": 0,
        "deletions": 0,
    }


@pytest.mark.asyncio
async def test_client_compares_repository_branches():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=COMPARE_RESPONSE)

    client = GitLabResourceClient(transport=httpx.MockTransport(respond))

    result = await client.compare_repository_branches(
        "https://gitlab.example.com",
        "glpat-secret-token",
        "team/api",
        from_ref="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
        to_ref="develop",
    )

    assert str(requests[0].url) == (
        "https://gitlab.example.com/api/v4/projects/team%2Fapi/repository/compare"
        "?from=4b825dc642cb6eb9a060e54bf8d69288fbee4904&to=develop"
    )
    assert requests[0].headers["PRIVATE-TOKEN"] == "glpat-secret-token"
    assert result == {"commitsCount": 3, "additions": 4, "deletions": 2}


@pytest.mark.asyncio
async def test_client_compare_missing_ref_raises_resource_error():
    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "404 ref not found"})

    client = GitLabResourceClient(transport=httpx.MockTransport(respond))

    with pytest.raises(GitLabResourceError) as exc_info:
        await client.compare_repository_branches(
            "https://gitlab.example.com",
            "glpat-secret-token",
            "team/api",
            from_ref="main",
            to_ref="deleted-branch",
        )

    assert exc_info.value.status_code == 404
