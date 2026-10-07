import asyncio
from typing import Any
from urllib.parse import quote

import httpx

from testing_agent_integration_worker.core.config import ControlPlaneSettings
from testing_agent_integration_worker.core.errors import ControlPlaneError
from testing_agent_integration_worker.schemas.job import Access, ClaimResponse, Identity, JobInput
from testing_agent_integration_worker.schemas.step import Permit, ResultEvent


class ControlPlaneRepository:
    def __init__(self, settings: ControlPlaneSettings, *, transport=None):
        self.http = httpx.AsyncClient(
            base_url=settings.base_url + "/internal/integration-worker/",
            headers={"X-Worker-Token": settings.worker_token.get_secret_value()},
            timeout=settings.timeout_seconds,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )
        self.attempts = settings.retry_attempts

    async def close(self) -> None:
        await self.http.aclose()

    async def request(self, method: str, path: str, *, body=None, params=None) -> dict[str, Any]:
        error = ControlPlaneError()
        for attempt in range(self.attempts):
            try:
                response = await self.http.request(method, path, json=body, params=params)
                if response.is_success:
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ControlPlaneError(502)
                    return data
                error = ControlPlaneError(response.status_code)
                if response.status_code < 500 and response.status_code != 429:
                    raise error
            except httpx.HTTPError:
                error = ControlPlaneError()
            except ValueError:
                error = ControlPlaneError(502)
            if attempt + 1 < self.attempts:
                await asyncio.sleep(0.1 * 2**attempt)
        raise error

    @staticmethod
    def root(job_id: str) -> str:
        return "jobs/" + quote(job_id, safe="")

    async def claim(self, worker_id: str, request_id: str) -> ClaimResponse:
        return ClaimResponse.model_validate(
            await self.request(
                "POST",
                "jobs/claim",
                body={
                    "workerId": worker_id,
                    "claimRequestId": request_id,
                    "protocolVersions": [1],
                    "taskTypes": ["zentao_bug_sync", "zentao_bug_fields_update"],
                },
            )
        )

    async def input(self, job_id: str, identity: Identity) -> JobInput:
        return JobInput.model_validate(
            await self.request(
                "GET", self.root(job_id) + "/input", params=identity.model_dump(by_alias=True)
            )
        )

    async def access(self, job_id: str, identity: Identity) -> Access:
        return Access.model_validate(
            await self.request(
                "POST", self.root(job_id) + "/access", body=identity.model_dump(by_alias=True)
            )
        )

    async def heartbeat(self, job_id: str, identity: Identity) -> float:
        data = await self.request(
            "POST", self.root(job_id) + "/heartbeat", body=identity.model_dump(by_alias=True)
        )
        seconds = data.get("leaseSeconds")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
            raise ControlPlaneError(502)
        return float(seconds)

    async def prepare(self, job_id: str, step_key: str, body: dict[str, Any]) -> Permit:
        path = self.root(job_id) + "/steps/" + quote(step_key, safe="") + "/prepare"
        return Permit.model_validate(await self.request("POST", path, body=body))

    async def result(
        self, job_id: str, step_key: str, event: ResultEvent, *, evidence=False
    ) -> dict[str, Any]:
        path = self.root(job_id) + "/steps/" + quote(step_key, safe="")
        return await self.request(
            "POST",
            path + ("/evidence" if evidence else "/result"),
            body=event.model_dump(mode="json", by_alias=True, exclude_none=True),
        )

    async def failure(self, job_id: str, step_key: str, body: dict[str, Any]) -> dict[str, Any]:
        path = self.root(job_id) + "/steps/" + quote(step_key, safe="") + "/preflight-failure"
        return await self.request("POST", path, body=body)

    async def completed(self, job_id: str, identity: Identity) -> dict[str, Any]:
        return await self.request(
            "POST", self.root(job_id) + "/completed", body=identity.model_dump(by_alias=True)
        )
