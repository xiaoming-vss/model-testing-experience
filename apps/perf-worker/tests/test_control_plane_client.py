from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from testing_agent_perf_worker.contracts.worker import DataFileRef
from testing_agent_perf_worker.control_plane.client import ControlPlaneClient
from testing_agent_perf_worker.core.config import Settings
from testing_agent_perf_worker.core.errors import DataFileError, LeaseLostError


def _settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.control_plane.base_url = "http://control-plane.test"
    settings.control_plane.worker_token = SecretStr("worker-token")
    settings.control_plane.timeout_seconds = 2
    settings.control_plane.retry_attempts = 2
    return settings


@pytest.mark.asyncio
async def test_claim_204_and_snapshot(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tasks/claim"):
            return httpx.Response(204)
        if request.url.path.endswith("/snapshot"):
            return httpx.Response(
                200,
                json={
                    "taskId": "task-1",
                    "runId": "run-1",
                    "caseName": "case",
                    "runSpec": {
                        "specVersion": "1.0",
                        "runId": "run-1",
                        "case": {
                            "name": "case",
                            "steps": [{"name": "ping", "method": "GET", "path": "/ping"}],
                            "load": {"model": "vus", "vus": 1, "duration": "1s"},
                            "acceptance": {
                                "source": "user_confirmed",
                                "confirmed": True,
                                "criteria": {"http_req_failed": ["rate<0.01"]},
                            },
                        },
                        "environment": {"baseUrl": "http://target.test", "variables": {}},
                        "remoteWrite": {"url": "http://prom.test/api/v1/write"},
                    },
                    "dataFiles": [],
                    "leaseSeconds": 60,
                },
            )
        raise AssertionError(request.url)

    client = ControlPlaneClient(_settings(tmp_path), transport=httpx.MockTransport(handler))
    try:
        assert await client.claim("worker-1") is None
        snapshot = await client.snapshot("task-1", "worker-1")
        assert snapshot.run_id == "run-1"
        assert snapshot.run_spec.environment.base_url == "http://target.test"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_rejection_does_not_echo_body_and_marks_lease_lost(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="private-body-and-token")

    client = ControlPlaneClient(_settings(tmp_path), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(LeaseLostError) as exc:
            await client.heartbeat("task-1", "worker-1")
        assert "private-body-and-token" not in str(exc.value)
        assert exc.value.status_code == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_download_data_file_verifies_and_writes_secure_file(tmp_path: Path):
    content = b"username,password\nu1,p1\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    client = ControlPlaneClient(_settings(tmp_path), transport=httpx.MockTransport(handler))
    destination = tmp_path / "inputs" / "users.csv"
    try:
        await client.download_data_file(
            "task-1",
            DataFileRef(
                file_id="file-1",
                filename="users.csv",
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            ),
            "worker-1",
            destination,
            max_bytes=1024,
        )
    finally:
        await client.close()
    assert destination.read_bytes() == content
    assert destination.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_download_data_file_rejects_hash_mismatch(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"wrong")

    client = ControlPlaneClient(_settings(tmp_path), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(DataFileError):
            await client.download_data_file(
                "task-1",
                DataFileRef(
                    file_id="file-1",
                    filename="users.csv",
                    size=5,
                    sha256="a" * 64,
                ),
                "worker-1",
                tmp_path / "users.csv",
                max_bytes=1024,
            )
    finally:
        await client.close()


@pytest.mark.parametrize("status", [429, 500, 501, 502, 503, 504, 505, 599])
@pytest.mark.asyncio
async def test_download_data_file_retries_retryable_status(tmp_path: Path, status: int):
    content = b"username,password\nu1,p1\n"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(status)
        return httpx.Response(200, content=content)

    client = ControlPlaneClient(_settings(tmp_path), transport=httpx.MockTransport(handler))
    destination = tmp_path / "inputs" / "users.csv"
    try:
        await client.download_data_file(
            "task-1",
            DataFileRef(
                file_id="file-1",
                filename="users.csv",
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            ),
            "worker-1",
            destination,
            max_bytes=1024,
        )
    finally:
        await client.close()

    assert calls == 2
    assert destination.read_bytes() == content


@pytest.mark.parametrize("status", [400, 403, 404, 409, 422])
@pytest.mark.asyncio
async def test_download_data_file_fails_fast_on_client_error(tmp_path: Path, status: int):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, text="private-body")

    client = ControlPlaneClient(_settings(tmp_path), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(LeaseLostError) as exc:
            await client.download_data_file(
                "task-1",
                DataFileRef(
                    file_id="file-1",
                    filename="users.csv",
                    size=6,
                    sha256="a" * 64,
                ),
                "worker-1",
                tmp_path / "users.csv",
                max_bytes=1024,
            )
    finally:
        await client.close()

    assert calls == 1
    assert "private-body" not in str(exc.value)
