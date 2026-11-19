from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from testing_agent.core.errors import AppError
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 19, 12, 0, 1, tzinfo=UTC)


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.active = False

    def start(self):
        self.active = True

    def in_transaction(self):
        return self.active

    async def scalar(self, statement):
        self.start()
        return None

    async def commit(self):
        self.commits += 1
        self.active = False

    async def rollback(self):
        self.rollbacks += 1
        self.active = False


class FakeRepository:
    def __init__(self, row=None):
        self.session = FakeSession()
        self.row = row
        self.added = []
        self.lock_reads = []
        self.concurrent_row = None

    async def get(self, user_id, provider, connection_id, project_id="", *, lock=False):
        self.session.start()
        self.lock_reads.append(lock)
        if lock and self.concurrent_row is not None:
            return self.concurrent_row
        return self.row

    def add(self, row):
        self.added.append(row)
        self.row = row

    async def commit(self):
        await self.session.commit()

    async def refresh(self, row):
        return None


class RecordingZentaoAuth:
    def __init__(self, repository):
        self.repository = repository
        self.commits_at_call = []

    async def authenticate(self, base_url, account, password, **kwargs):
        self.commits_at_call.append(
            (self.repository.session.commits, self.repository.session.in_transaction())
        )
        return SimpleNamespace(access_token="new-token", expires_at=None)


class RecordingGitLabAuth:
    def __init__(self, repository, *, concurrent_row=None):
        self.repository = repository
        self.concurrent_row = concurrent_row
        self.commits_at_call = []

    async def validate(self, base_url, access_token, **kwargs):
        self.commits_at_call.append(
            (self.repository.session.commits, self.repository.session.in_transaction())
        )
        if self.concurrent_row is not None:
            self.repository.concurrent_row = self.concurrent_row


def gitlab_row(updated_at=NOW):
    return SimpleNamespace(
        connection_id="connection-1",
        project_id="",
        user_id="user-1",
        provider="gitlab",
        name="公司 GitLab",
        base_url="https://gitlab.example",
        auth_type="personal_access_token",
        account="",
        secret_json={},
        access_token=IntegrationCredentialCipher("test-key").encrypt("old-token"),
        status="active",
        last_auth_at=None,
        last_auth_error="",
        extra_json={"allowHttp": False, "insecureSkipVerify": False},
        created_at=NOW,
        updated_at=updated_at,
    )


@pytest.mark.asyncio
async def test_zentao_connection_create_commits_before_external_authentication():
    repository = FakeRepository()
    auth = RecordingZentaoAuth(repository)
    service = IntegrationConnectionService(
        repository,
        zentao_auth_provider=auth,
        credential_cipher=IntegrationCredentialCipher("test-key"),
    )

    await service.create(
        "zentao",
        {
            "name": "公司禅道",
            "baseUrl": "https://zentao.example",
            "account": "tester",
            "password": "secret",
        },
        "user-1",
    )

    assert auth.commits_at_call == [(1, False)]
    assert repository.session.commits == 2


@pytest.mark.asyncio
async def test_gitlab_connection_update_commits_before_external_validation_and_relocks():
    repository = FakeRepository(gitlab_row())
    auth = RecordingGitLabAuth(repository)
    service = IntegrationConnectionService(
        repository,
        gitlab_auth_provider=auth,
        credential_cipher=IntegrationCredentialCipher("test-key"),
    )

    await service.update(
        "gitlab",
        "connection-1",
        {"accessToken": "new-token"},
        "user-1",
    )

    assert auth.commits_at_call == [(1, False)]
    assert repository.lock_reads[-1] is True
    assert repository.session.commits == 2


@pytest.mark.asyncio
async def test_gitlab_reauthentication_commits_before_external_validation_and_relocks():
    repository = FakeRepository(gitlab_row())
    auth = RecordingGitLabAuth(repository)
    service = IntegrationConnectionService(
        repository,
        gitlab_auth_provider=auth,
        credential_cipher=IntegrationCredentialCipher("test-key"),
    )

    await service.reauth_gitlab("connection-1", None, "user-1")

    assert auth.commits_at_call == [(1, False)]
    assert repository.lock_reads[-1] is True
    assert repository.session.commits == 2


@pytest.mark.asyncio
async def test_connection_update_rejects_a_change_made_during_external_validation():
    repository = FakeRepository(gitlab_row())
    concurrent = gitlab_row(LATER)
    concurrent.name = "并发修改后的名称"
    auth = RecordingGitLabAuth(repository, concurrent_row=concurrent)
    service = IntegrationConnectionService(
        repository,
        gitlab_auth_provider=auth,
        credential_cipher=IntegrationCredentialCipher("test-key"),
    )
    original_token = concurrent.access_token

    with pytest.raises(AppError) as exc:
        await service.update(
            "gitlab",
            "connection-1",
            {"accessToken": "new-token"},
            "user-1",
        )

    assert exc.value.http_code == 409
    assert repository.lock_reads[-1] is True
    assert concurrent.name == "并发修改后的名称"
    assert concurrent.access_token == original_token
