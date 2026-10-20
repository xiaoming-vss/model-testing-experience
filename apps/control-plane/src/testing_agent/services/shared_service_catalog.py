"""Read catalog state with bounded remote probes and serialized database access."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import AppError
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.shared_service import SharedService
from testing_agent.repositories.shared_service_catalog import SharedServiceCatalogRepository
from testing_agent.services.personal_credentials import PersonalCredentialAccess

PROBE_CONCURRENCY = 4
type DiscoverInstance = Callable[[str, str], Awaitable[dict[str, Any]]]
type NeedsInstanceReset = Callable[[AsyncSession, SharedService, dict[str, Any]], Awaitable[bool]]


@dataclass(frozen=True)
class ProbeRequest:
    endpoint: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class ProbeResult:
    instance: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    probed: bool = False


class SharedServiceCatalog:
    def __init__(
        self,
        repository: SharedServiceCatalogRepository,
        credentials: PersonalCredentialAccess,
        *,
        discover: DiscoverInstance,
        needs_reset: NeedsInstanceReset,
    ) -> None:
        self.repository = repository
        self.credentials = credentials
        self.discover = discover
        self.needs_reset = needs_reset

    async def read(self, resources: Sequence[SharedService], user_id: str) -> list[dict[str, Any]]:
        owned = await self.repository.owned_connections(resources, user_id)
        # Materialize ordinary inputs before any concurrent work. No ORM or
        # AsyncSession access occurs inside a probe coroutine.
        requests: list[ProbeRequest | ProbeResult] = []
        for resource in resources:
            own = owned.get(resource.service_id)
            if resource.provider != "mcp":
                requests.append(ProbeResult())
            elif own and own.status == "active" and (own.secret_json or {}).get("token"):
                try:
                    token = self.credentials.mcp_token(
                        own, user_id=user_id, project_id=resource.project_id
                    )
                    requests.append(ProbeRequest(resource.base_url, token))
                except AppError as exc:
                    requests.append(ProbeResult(error=exc.message))
            else:
                requests.append(ProbeResult(error="保存本人的 Token 后自动读取禅道实例"))
        semaphore = asyncio.Semaphore(PROBE_CONCURRENCY)

        async def probe(request: ProbeRequest | ProbeResult) -> ProbeResult:
            if isinstance(request, ProbeResult):
                return request
            async with semaphore:
                try:
                    return ProbeResult(
                        await self.discover(request.endpoint, request.token), probed=True
                    )
                except AppError as exc:
                    return ProbeResult(error=exc.message)

        tasks = [asyncio.create_task(probe(request)) for request in requests]
        try:
            observations = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        # Association/instance checks use the same transaction sequentially.
        return [
            await self._describe(resource, owned.get(resource.service_id), observation)
            for resource, observation in zip(resources, observations, strict=True)
        ]

    async def _describe(
        self, resource: SharedService, own: IntegrationConnection | None, observation: ProbeResult
    ) -> dict[str, Any]:
        authorization: dict[str, Any] = {"status": "unauthorized"}
        if own is not None:
            authorization = {
                "status": "authorized" if own.status == "active" else "invalid",
                "connectionId": own.connection_id,
                "account": own.account,
                "lastAuthAt": own.last_auth_at,
            }
        instance, instance_error = observation.instance, observation.error
        reset_required, pending_instance = False, ""
        if observation.probed:
            try:
                if await self.needs_reset(self.repository.session, resource, instance):
                    reset_required = True
                    pending_instance = instance["instanceUrl"]
                    instance = {}
                    instance_error = (
                        "禅道目标已变更或存在旧绑定，请项目所有者在编辑服务中勾选确认后保存"
                    )
            except AppError as exc:
                instance = {}
                instance_error = exc.message
        return {
            "serviceId": resource.service_id,
            "projectId": resource.project_id,
            "provider": resource.provider,
            "name": resource.name,
            "baseUrl": resource.base_url,
            "modelId": resource.model_id,
            "templateId": resource.template_id,
            "zentaoInstanceUrl": instance.get("instanceUrl", ""),
            "zentaoApiBaseUrl": instance.get("apiBaseUrl", ""),
            "instanceError": instance_error,
            "instanceResetRequired": reset_required,
            "pendingInstanceUrl": pending_instance,
            "connectionStatus": "available"
            if instance
            else ("error" if own and own.status == "active" else "unchecked"),
            "authorization": authorization,
        }
