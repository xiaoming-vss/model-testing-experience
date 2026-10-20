from unittest.mock import Mock

import pytest

from testing_agent.core.errors import ErrIntegrationConnectionAuthFailed, ErrNotFound
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.personal_credentials import PersonalCredentialAccess


def connection(**changes):
    return IntegrationConnection(
        **{
            "connection_id": "personal",
            "user_id": "owner",
            "provider": "mcp",
            "project_id": "project",
            "status": "active",
            "secret_json": {"token": "ciphertext"},
            **changes,
        }
    )


@pytest.mark.parametrize(
    "changes,user_id,project_id",
    [
        ({}, "someone-else", "project"),
        ({}, "super-admin", "project"),
        ({}, "", "project"),
        ({}, "owner", "other-project"),
        ({}, "owner", ""),
        ({"provider": "gitlab"}, "owner", "project"),
    ],
)
def test_mcp_credentials_reject_wrong_actor_scope_or_provider_before_decryption(
    changes, user_id, project_id
):
    cipher = Mock(spec=IntegrationCredentialCipher)
    access = PersonalCredentialAccess(cipher)
    with pytest.raises(type(ErrNotFound)):
        access.mcp_token(connection(**changes), user_id=user_id, project_id=project_id)
    cipher.decrypt.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "auth_failed"},
        {"secret_json": None},
        {"secret_json": {"token": ""}},
        {"secret_json": {"token": {"invalid": "shape"}}},
    ],
)
def test_mcp_credentials_reject_inactive_or_missing_token_before_decryption(changes):
    cipher = Mock(spec=IntegrationCredentialCipher)
    with pytest.raises(type(ErrIntegrationConnectionAuthFailed)):
        PersonalCredentialAccess(cipher).mcp_token(
            connection(**changes), user_id="owner", project_id="project"
        )
    cipher.decrypt.assert_not_called()


@pytest.mark.parametrize("stored_project", ["", "project"])
def test_mcp_credentials_decrypt_only_the_selected_personal_token(stored_project):
    cipher = IntegrationCredentialCipher("personal-credential-test-key")
    row = connection(project_id=stored_project, secret_json={"token": cipher.encrypt("test-token")})
    access = PersonalCredentialAccess(cipher)
    assert access.mcp_token(row, user_id="owner", project_id="project") == "test-token"
    assert row.secret_json["token"] != "test-token"


def test_mcp_credentials_do_not_fall_back_to_ciphertext_or_plaintext():
    cipher = IntegrationCredentialCipher("personal-credential-test-key")
    access = PersonalCredentialAccess(cipher)
    with pytest.raises(ValueError, match="集成凭据无法解密"):
        access.mcp_token(
            connection(secret_json={"token": "unprotected-token"}),
            user_id="owner",
            project_id="project",
        )


@pytest.mark.parametrize("project_id", ["project", ""])
def test_gitlab_selected_owner_connection_preserves_standalone_lookup(project_id):
    cipher = IntegrationCredentialCipher("personal-credential-test-key")
    row = connection(provider="gitlab", access_token=cipher.encrypt("test-pat"))
    assert (
        PersonalCredentialAccess(cipher).gitlab_token(row, user_id="owner", project_id=project_id)
        == "test-pat"
    )


@pytest.mark.parametrize(
    "user_id,project_id,status",
    [
        ("other", "project", "active"),
        ("owner", "other-project", "active"),
        ("owner", "project", "auth_failed"),
    ],
)
def test_gitlab_token_never_decrypts_outside_current_personal_authorization(
    user_id, project_id, status
):
    cipher = Mock(spec=IntegrationCredentialCipher)
    row = connection(provider="gitlab", status=status, access_token="ciphertext")
    error = ErrIntegrationConnectionAuthFailed if status != "active" else ErrNotFound
    with pytest.raises(type(error)):
        PersonalCredentialAccess(cipher).gitlab_token(row, user_id=user_id, project_id=project_id)
    cipher.decrypt.assert_not_called()
