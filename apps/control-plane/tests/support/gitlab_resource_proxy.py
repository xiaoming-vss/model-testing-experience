"""Shared preparation for gitlab resource proxy tests; no collected cases."""

from types import SimpleNamespace

from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from testing_agent.api.deps import get_current_user_id, get_integration_connection_service
from testing_agent.app import create_app
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
