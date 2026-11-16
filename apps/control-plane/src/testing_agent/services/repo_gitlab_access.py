"""Resolve a software repository with the current actor's personal credentials."""

from __future__ import annotations

from typing import NamedTuple

from testing_agent.core.errors import ErrResourceBindingInvalid
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher


class RepoGitlabAccess(NamedTuple):
    connection_id: str
    base_url: str
    access_token: str


async def resolve_repo_gitlab_access(
    integration_connection_service: IntegrationConnectionService,
    credential_cipher: IntegrationCredentialCipher,
    project_id: str,
    software_repository: SoftwareRepository,
    *,
    user_id: str,
    connection_id: str = "",
) -> RepoGitlabAccess:
    if (
        not software_repository.repository_instance_url
        or not software_repository.repository_project_id
    ):
        raise ErrResourceBindingInvalid()
    connection = await integration_connection_service.resolve_personal_connection(
        user_id,
        "gitlab",
        project_id,
        software_repository.repository_instance_url,
        connection_id,
    )
    token = credential_cipher.decrypt(connection.access_token)
    return RepoGitlabAccess(connection.connection_id, connection.base_url, token)
