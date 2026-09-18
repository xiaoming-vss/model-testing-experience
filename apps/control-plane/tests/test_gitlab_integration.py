from types import SimpleNamespace

import httpx
import pytest
from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from testing_agent.api.deps import get_current_user_id, get_integration_connection_service
from testing_agent.app import create_app
from testing_agent.services.gitlab_auth import GitLabAuthProvider
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher

PROJECT_CONNECTIONS_URL = "/v1/projects/project-1/integrations/gitlab/connections"


class FakeIntegrationConnectionRepository:
    session = AuthorizationDatabase()

    def __init__(self):
        self.rows = []

    async def get(self, user_id, provider, connection_id, project_id=""):
        return next(
            (
                row
                for row in self.rows
                if row.user_id == user_id
                and row.provider == provider
                and row.connection_id == connection_id
                and (not project_id or row.project_id == project_id)

            ),
            None,
        )

    async def list(self, user_id, provider, project_id=""):
        return [
            row
            for row in self.rows
            if row.user_id == user_id
            and row.provider == provider
            and (not project_id or row.project_id == project_id)

        ]

    async def get_project(self, project_id):
        if project_id != "project-1":
            return None
        return SimpleNamespace(project_id=project_id, user_id="user-1")

    def add(self, connection):
        self.rows.append(connection)

    async def hard_delete(self, row):
        self.rows.remove(row)

    async def commit(self):
        return None

    async def refresh(self, connection):
        return None


class AcceptingGitLabAuthProvider:
    def __init__(self):
        self.validated = []

    async def validate(self, base_url, access_token):
        self.validated.append((base_url, access_token))


class RejectingGitLabAuthProvider:
    async def validate(self, base_url, access_token):
        raise RuntimeError("GitLab 鉴权失败，HTTP 401")


def gitlab_client(repository, auth_provider, cipher):
    app = create_app()
    service = IntegrationConnectionService(
        repository,
        gitlab_auth_provider=auth_provider,
        credential_cipher=cipher,
    )
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_integration_connection_service] = lambda: service
    return TestClient(app)


def test_integration_credential_cipher_round_trips_without_exposing_plaintext():
    cipher = IntegrationCredentialCipher("stable-production-secret")

    encrypted = cipher.encrypt("glpat-secret-token")

    assert encrypted.startswith("enc:v1:")
    assert "glpat-secret-token" not in encrypted
    assert cipher.decrypt(encrypted) == "glpat-secret-token"


def test_integration_credential_cipher_rejects_a_different_key():
    encrypted = IntegrationCredentialCipher("first-key").encrypt("glpat-secret-token")

    with pytest.raises(ValueError, match="无法解密"):
        IntegrationCredentialCipher("second-key").decrypt(encrypted)


@pytest.mark.parametrize(
    "secret",
    ["", "change-me", "replace-with-local-integration-key"],
)
def test_integration_credential_cipher_rejects_missing_or_placeholder_keys(secret):
    with pytest.raises(ValueError, match="安全的集成凭据加密密钥"):
        IntegrationCredentialCipher(secret)


@pytest.mark.asyncio
async def test_gitlab_auth_validates_with_user_endpoint_without_returning_profile():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"id": 42, "username": "zhangsan", "name": "张三"},
        )

    provider = GitLabAuthProvider(transport=httpx.MockTransport(respond))

    result = await provider.validate(
        "https://gitlab.example.com/",
        "glpat-secret-token",
    )

    assert result is None
    assert str(requests[0].url) == "https://gitlab.example.com/api/v4/user"
    assert requests[0].headers["PRIVATE-TOKEN"] == "glpat-secret-token"


def test_user_creates_a_gitlab_connection_with_an_encrypted_token():
    repository = FakeIntegrationConnectionRepository()
    auth_provider = AcceptingGitLabAuthProvider()
    cipher = IntegrationCredentialCipher("integration-key")
    client = gitlab_client(repository, auth_provider, cipher)

    response = client.post(
        PROJECT_CONNECTIONS_URL,
        json={
            "name": "公司 GitLab",
            "baseUrl": "https://gitlab.example.com/",
            "accessToken": "glpat-secret-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["projectId"] == "project-1"
    assert (
        response.json()["data"]
        | {
            "provider": "gitlab",
            "name": "公司 GitLab",
            "baseUrl": "https://gitlab.example.com",
            "authType": "personal_access_token",
            "status": "active",
            "hasAccessToken": True,
        }
        == response.json()["data"]
    )
    assert "accessToken" not in response.json()["data"]
    assert auth_provider.validated == [("https://gitlab.example.com", "glpat-secret-token")]
    assert repository.rows[0].access_token != "glpat-secret-token"
    assert cipher.decrypt(repository.rows[0].access_token) == "glpat-secret-token"


def test_invalid_gitlab_token_does_not_create_a_connection():
    repository = FakeIntegrationConnectionRepository()
    client = gitlab_client(
        repository,
        RejectingGitLabAuthProvider(),
        IntegrationCredentialCipher("integration-key"),
    )

    response = client.post(
        PROJECT_CONNECTIONS_URL,
        json={
            "name": "公司 GitLab",
            "baseUrl": "https://gitlab.example.com",
            "accessToken": "expired-token",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == 3403
    assert repository.rows == []


def test_user_updates_a_gitlab_connection_only_after_new_credentials_validate():
    repository = FakeIntegrationConnectionRepository()
    auth_provider = AcceptingGitLabAuthProvider()
    cipher = IntegrationCredentialCipher("integration-key")
    client = gitlab_client(repository, auth_provider, cipher)
    created = client.post(
        PROJECT_CONNECTIONS_URL,
        json={
            "name": "公司 GitLab",
            "baseUrl": "https://gitlab.old.example",
            "accessToken": "old-token",
        },
    ).json()["data"]
    auth_provider.validated.clear()

    response = client.patch(
        f"{PROJECT_CONNECTIONS_URL}/{created['connectionId']}",
        json={
            "baseUrl": "https://gitlab.new.example/",
            "accessToken": "new-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["baseUrl"] == "https://gitlab.new.example"
    assert auth_provider.validated == [("https://gitlab.new.example", "new-token")]
    assert cipher.decrypt(repository.rows[0].access_token) == "new-token"


def test_user_reauthenticates_with_the_decrypted_stored_gitlab_token():
    repository = FakeIntegrationConnectionRepository()
    auth_provider = AcceptingGitLabAuthProvider()
    cipher = IntegrationCredentialCipher("integration-key")
    client = gitlab_client(repository, auth_provider, cipher)
    created = client.post(
        PROJECT_CONNECTIONS_URL,
        json={
            "name": "公司 GitLab",
            "baseUrl": "https://gitlab.example.com",
            "accessToken": "glpat-secret-token",
        },
    ).json()["data"]
    auth_provider.validated.clear()

    response = client.post(f"{PROJECT_CONNECTIONS_URL}/{created['connectionId']}/reauth")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "active"
    assert "accessToken" not in response.json()["data"]
    assert auth_provider.validated == [("https://gitlab.example.com", "glpat-secret-token")]


def test_user_lists_gets_and_deletes_a_gitlab_connection():
    repository = FakeIntegrationConnectionRepository()
    client = gitlab_client(
        repository,
        AcceptingGitLabAuthProvider(),
        IntegrationCredentialCipher("integration-key"),
    )
    created = client.post(
        PROJECT_CONNECTIONS_URL,
        json={
            "name": "公司 GitLab",
            "baseUrl": "https://gitlab.example.com",
            "accessToken": "glpat-secret-token",
        },
    ).json()["data"]

    listed = client.get(PROJECT_CONNECTIONS_URL)
    fetched = client.get(f"{PROJECT_CONNECTIONS_URL}/{created['connectionId']}")
    deleted = client.delete(f"{PROJECT_CONNECTIONS_URL}/{created['connectionId']}")
    missing = client.get(f"{PROJECT_CONNECTIONS_URL}/{created['connectionId']}")

    assert [item["connectionId"] for item in listed.json()["data"]["items"]] == [
        created["connectionId"]
    ]
    assert fetched.json()["data"]["connectionId"] == created["connectionId"]
    assert deleted.status_code == 200
    assert deleted.json()["data"] == {}
    assert missing.status_code == 404


def test_gitlab_only_exposes_project_scoped_connections_and_keeps_zentao_routes():
    paths = create_app().openapi()["paths"]

    assert not any(path.startswith("/v1/integrations/gitlab/") for path in paths)
    assert "post" not in paths["/v1/integrations/zentao/connections"]
    assert "post" in paths["/v1/projects/{projectId}/integrations/gitlab/connections"]
