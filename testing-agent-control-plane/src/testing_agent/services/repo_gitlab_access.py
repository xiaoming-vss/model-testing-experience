"""Resolve a bound repository with the current actor's personal credentials."""

from __future__ import annotations

from typing import NamedTuple

from testing_agent.core.errors import ErrResourceBindingInvalid
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher


class RepoGitlabAccess(NamedTuple):
    connection_id: str
    base_url: str
    access_token: str


async def resolve_repo_gitlab_access(
    binding_repository: ResourceBindingRepository,
    integration_connection_service: IntegrationConnectionService,
    credential_cipher: IntegrationCredentialCipher,
    project_id: str,
    binding: ResourceBinding,
    *,
    user_id: str,
    connection_id: str = "",
) -> RepoGitlabAccess:
    if not binding.instance_url or not binding.remote_parent_id:
        raise ErrResourceBindingInvalid
    group = await binding_repository.get_active_project_group_binding(
        "gitlab", project_id, binding.remote_parent_id, instance=binding.instance_key
    )
    if group is None:
        raise ErrResourceBindingInvalid
    connection = await integration_connection_service.resolve_personal_connection(
        user_id, "gitlab", project_id, binding.instance_url, connection_id
    )
    token = credential_cipher.decrypt(connection.access_token)
    return RepoGitlabAccess(connection.connection_id, connection.base_url, token)
