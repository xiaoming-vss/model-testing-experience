"""Binding serialization, access contract, and explicit commit error translation."""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import ErrRemoteResourceAlreadyBound
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.services.project_access import ProjectAction
from testing_agent.services.zentao_mcp_selection import binding_service_id


class LocalBindingAccess(Protocol):
    async def __call__(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        *,
        action: ProjectAction = "manage",
    ) -> str: ...


def dump_binding(binding: ResourceBinding) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "bindingId": binding.binding_id,
        "instanceUrl": binding.instance_url,
        "provider": binding.provider,
        "connectionId": binding.connection_id,
        "mcpServiceId": binding_service_id(binding),
        "localResourceType": binding.local_resource_type,
        "localResourceId": binding.local_resource_id,
        "remoteResourceType": binding.remote_resource_type,
        "remoteResourceId": binding.remote_resource_id,
        "remoteParentId": binding.remote_parent_id,
        "remoteNameSnapshot": binding.remote_name_snapshot,
        "status": binding.status,
        "boundAt": binding.bound_at,
        "lastVerifiedAt": binding.last_verified_at,
        "createdAt": binding.created_at,
        "updatedAt": binding.updated_at,
    }
    if binding.remote_resource_type == "repository":
        extra = getattr(binding, "extra_json", None) or {}
        payload["branch"] = str(extra.get("branch") or "")
        payload["baselineBranch"] = str(
            extra.get("baseline_branch") or extra.get("baselineBranch") or ""
        )
    return payload


async def commit_binding(repository: ResourceBindingRepository) -> None:
    try:
        await repository.commit()
    except IntegrityError as exc:
        await repository.rollback()
        # Translate only our known uniqueness constraint, not unrelated DB errors.
        if "uq_binding_resource" in str(
            exc.orig
        ) or "UNIQUE constraint failed: resource_bindings." in str(exc.orig):
            raise ErrRemoteResourceAlreadyBound() from exc
        raise
