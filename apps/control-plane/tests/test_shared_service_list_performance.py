import asyncio
import time

import pytest
from sqlalchemy import event
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.repositories.integration_connection import IntegrationConnectionRepository
from testing_agent.repositories.shared_service_catalog import SharedServiceCatalogRepository
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.shared_service import SharedServiceService


def seeded_catalog(db, count):
    cipher = IntegrationCredentialCipher("shared-list-test-key")
    for index in range(count):
        db.add(
            SharedService(
                service_id=f"service-{index}",
                project_id="p",
                provider="mcp",
                name=f"Service {index}",
                base_url=f"https://mcp-{index}.test",
                template_id="zentao",
            )
        )
        db.add(
            IntegrationConnection(
                connection_id=f"personal-{index}",
                user_id="u",
                project_id="p",
                provider="mcp",
                name=f"MCP {index}",
                status="active",
                secret_json={"token": cipher.encrypt("test-token")},
            )
        )
    db.flush()
    for index in range(count):
        db.add(
            ServiceAuthorization(
                service_id=f"service-{index}", user_id="u", connection_id=f"personal-{index}"
            )
        )
    db.commit()
    return SharedServiceService(
        IntegrationConnectionService(
            IntegrationConnectionRepository(AsyncSessionAdapter(db)), credential_cipher=cipher
        )
    )


@pytest.mark.parametrize("count", [4, 8])
async def test_shared_service_list_probe_cost(db, monkeypatch, count):
    service = seeded_catalog(db, count)
    expected_order = [
        row.service_id
        for row in await SharedServiceCatalogRepository(service.session).resources("p", "mcp")
    ]
    measurements = {
        "queries": 0,
        "calls": 0,
        "in_flight": 0,
        "max_in_flight": 0,
        "queries_during_probe": 0,
    }

    def query(*args):
        measurements["queries"] += 1
        if measurements["in_flight"]:
            measurements["queries_during_probe"] += 1

    async def discover(endpoint, token):
        assert token == "test-token"
        measurements["calls"] += 1
        measurements["in_flight"] += 1
        measurements["max_in_flight"] = max(
            measurements["max_in_flight"], measurements["in_flight"]
        )
        try:
            await asyncio.sleep(0.05)
            return {"instanceUrl": "https://zentao.test", "apiBaseUrl": "https://zentao.test/api"}
        finally:
            measurements["in_flight"] -= 1

    monkeypatch.setattr("testing_agent.services.shared_service.discover_instance", discover)
    event.listen(db.bind, "before_cursor_execute", query)
    try:
        started = time.monotonic()
        result = await service.list("u", "p", "mcp")
        measurements["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    finally:
        event.remove(db.bind, "before_cursor_execute", query)
    print({"services": count, **measurements})
    assert result["total"] == count
    assert measurements["calls"] == count
    assert measurements["queries_during_probe"] == 0
    assert all(row["connectionStatus"] == "available" for row in result["items"])
    assert measurements["max_in_flight"] == min(count, 4)
    assert measurements["queries"] < 6 * count + 2  # Measured serial baseline.
    assert [row["serviceId"] for row in result["items"]] == expected_order


async def test_probe_error_is_local_to_one_service_and_preserves_order(db, monkeypatch):
    service = seeded_catalog(db, 4)
    expected = [
        row.service_id
        for row in await SharedServiceCatalogRepository(service.session).resources("p", "mcp")
    ]

    async def discover(endpoint, token):
        if endpoint == "https://mcp-0.test":
            raise AppError(502, "test remote unavailable", 502)
        await asyncio.sleep(0.001)
        return {"instanceUrl": "https://zentao.test", "apiBaseUrl": "https://zentao.test/api"}

    monkeypatch.setattr("testing_agent.services.shared_service.discover_instance", discover)
    result = await service.list("u", "p", "mcp")
    assert [row["serviceId"] for row in result["items"]] == expected
    rows = {row["serviceId"]: row for row in result["items"]}
    assert rows["service-0"]["connectionStatus"] == "error"
    assert rows["service-0"]["instanceError"] == "test remote unavailable"
    assert all(rows[f"service-{i}"]["connectionStatus"] == "available" for i in range(1, 4))


@pytest.mark.parametrize("cancel_request", [False, True])
async def test_probe_failure_or_request_cancellation_drains_other_probes(
    db, monkeypatch, cancel_request
):
    service = seeded_catalog(db, 4)
    ready = asyncio.Event()
    pending = asyncio.Event()
    started, finished = set(), set()

    async def discover(endpoint, token):
        started.add(endpoint)
        if len(started) == 4:
            ready.set()
        try:
            await ready.wait()
            if not cancel_request and endpoint == "https://mcp-0.test":
                raise RuntimeError("unexpected probe failure")
            await pending.wait()
        finally:
            finished.add(endpoint)

    monkeypatch.setattr("testing_agent.services.shared_service.discover_instance", discover)
    request = asyncio.create_task(service.list("u", "p", "mcp"))
    try:
        await asyncio.wait_for(ready.wait(), timeout=2)
        if cancel_request:
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
        else:
            with pytest.raises(RuntimeError, match="unexpected probe failure"):
                await asyncio.wait_for(request, timeout=2)
    finally:
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
    assert len(started) == 4
    assert finished == started
