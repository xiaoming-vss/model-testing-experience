"""HTTP client for the control-plane perf worker protocol."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any

import httpx

from ..contracts.worker import (
    ClaimRequest,
    ClaimResponse,
    ControlResponse,
    DataFileRef,
    HeartbeatRequest,
    HeartbeatResponse,
    SnapshotResponse,
    StartedRequest,
)
from ..core.config import Settings
from ..core.errors import (
    ConfigError,
    ControlPlaneError,
    DataFileError,
    LeaseLostError,
)

_LEASE_REJECTION_STATUSES = {400, 401, 403, 404, 409, 422}


class ControlPlaneClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        base_url = settings.control_plane.base_url.strip()
        token = settings.control_plane.worker_token.get_secret_value()
        if not base_url:
            raise ConfigError("poll 模式缺少 [control_plane].base_url")
        if not token:
            raise ConfigError("poll 模式缺少 [control_plane].worker_token")
        self._attempts = settings.control_plane.retry_attempts
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/internal/perf-worker/",
            headers={"X-Worker-Token": token},
            timeout=settings.control_plane.timeout_seconds,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def claim(self, worker_id: str) -> ClaimResponse | None:
        response = await self._request(
            "POST", "tasks/claim", json=ClaimRequest(worker_id=worker_id).model_dump(by_alias=True)
        )
        if response.status_code == 204:
            return None
        return ClaimResponse.model_validate(self._json(response))

    async def snapshot(self, task_id: str, worker_id: str) -> SnapshotResponse:
        response = await self._request(
            "GET",
            f"tasks/{task_id}/snapshot",
            params={"workerId": worker_id},
        )
        return SnapshotResponse.model_validate(self._json(response))

    async def started(self, task_id: str, worker_id: str, started_at: str) -> None:
        await self._request(
            "POST",
            f"tasks/{task_id}/started",
            json=StartedRequest(worker_id=worker_id, started_at=started_at).model_dump(
                by_alias=True
            ),
        )

    async def heartbeat(self, task_id: str, worker_id: str) -> HeartbeatResponse:
        response = await self._request(
            "POST",
            f"tasks/{task_id}/heartbeat",
            json=HeartbeatRequest(worker_id=worker_id).model_dump(by_alias=True),
        )
        return HeartbeatResponse.model_validate(self._json(response))

    async def control(self, task_id: str, worker_id: str) -> ControlResponse:
        response = await self._request(
            "GET",
            f"tasks/{task_id}/control",
            params={"workerId": worker_id},
        )
        return ControlResponse.model_validate(self._json(response))

    async def complete(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"tasks/{task_id}/completed",
            json=payload,
        )
        return self._json(response)

    async def download_data_file(
        self,
        task_id: str,
        file: DataFileRef,
        worker_id: str,
        destination: Path,
        *,
        max_bytes: int,
    ) -> None:
        if file.size > max_bytes:
            raise DataFileError(f"数据文件超过大小限制: {file.filename}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None
        for attempt in range(self._attempts):
            part = destination.with_name(destination.name + f".part-{attempt}")
            try:
                await self._download_once(task_id, file, worker_id, part, max_bytes)
                os.chmod(part, 0o600)
                os.replace(part, destination)
                return
            except (ControlPlaneError, DataFileError, httpx.HTTPError, OSError) as exc:
                last_error = exc
                try:
                    part.unlink(missing_ok=True)
                except OSError:
                    pass
                if isinstance(exc, ControlPlaneError) and exc.status_code:
                    raise
                if attempt + 1 < self._attempts:
                    await asyncio.sleep(0.1 * (2**attempt))
        if isinstance(last_error, ControlPlaneError | DataFileError):
            raise last_error
        raise DataFileError(f"下载数据文件失败: {file.filename}") from last_error

    async def _download_once(
        self,
        task_id: str,
        file: DataFileRef,
        worker_id: str,
        destination: Path,
        max_bytes: int,
    ) -> None:
        digest = hashlib.sha256()
        count = 0
        async with self._client.stream(
            "GET",
            f"tasks/{task_id}/data-files/{file.file_id}",
            params={"workerId": worker_id},
            timeout=httpx.Timeout(connect=10, read=120, write=30, pool=10),
        ) as response:
            self._raise_for_status(response.status_code)
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as stream:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    count += len(chunk)
                    if count > max_bytes:
                        raise DataFileError(f"数据文件超过大小限制: {file.filename}")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
        if count != file.size or digest.hexdigest() != file.sha256:
            raise DataFileError(f"数据文件校验失败: {file.filename}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._attempts):
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt + 1 < self._attempts:
                    await asyncio.sleep(0.1 * (2**attempt))
                    continue
                raise ControlPlaneError("控制面请求失败") from None
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = ControlPlaneError("控制面暂时不可用", response.status_code)
                if attempt + 1 < self._attempts:
                    await asyncio.sleep(0.1 * (2**attempt))
                    continue
                raise last_error
            self._raise_for_status(response.status_code)
            return response
        raise ControlPlaneError("控制面请求失败") from last_error

    def _raise_for_status(self, status_code: int) -> None:
        if status_code < 400:
            return
        if status_code in _LEASE_REJECTION_STATUSES:
            raise LeaseLostError("控制面已拒绝当前执行租约", status_code)
        raise ControlPlaneError("控制面请求失败", status_code)

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            raise ControlPlaneError("控制面返回了非法 JSON", 502) from None
        if not isinstance(payload, dict):
            raise ControlPlaneError("控制面返回了非法 JSON", 502)
        return payload
