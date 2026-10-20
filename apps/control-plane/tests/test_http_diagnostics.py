import asyncio
import json
import logging
import traceback
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from testing_agent.core.http_diagnostics import (
    LOGGER_NAME,
    RequestDiagnosticsMiddleware,
    ResponseAborted,
    current_request_id,
)


@pytest.fixture(autouse=True)
def diagnostic_log_capture(monkeypatch, caplog):
    # Alembic's fileConfig disables existing named loggers in migration tests.
    # Capture this module's records explicitly, independent of preceding tests
    # or production's non-propagating handler; restore every setting afterwards.
    logger = logging.getLogger(LOGGER_NAME)
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(logger, "propagate", False)
    monkeypatch.setattr(logger, "handlers", [caplog.handler])


def records(caplog):
    return [json.loads(record.message) for record in caplog.records if record.name == LOGGER_NAME]


def sample_app():
    app = FastAPI()
    app.add_middleware(RequestDiagnosticsMiddleware)

    @app.get("/items/{item_id}")
    async def item(item_id: str, request: Request):
        await asyncio.sleep(0)
        assert request.state.request_id == current_request_id()
        return {"request_id": current_request_id()}

    @app.get("/broken")
    async def broken():
        try:
            raise ValueError("secret credential in cause")
        except ValueError as cause:
            raise RuntimeError("secret SQL query") from cause

    @app.get("/stream")
    async def stream():
        async def content():
            yield b"first"
            raise RuntimeError("secret streaming message")

        return StreamingResponse(content())

    @app.post("/internal/ai-worker/tasks/claim")
    async def claim():
        return {}

    return app


def test_unknown_error_records_one_safe_trace_and_keeps_envelope(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    response = TestClient(sample_app()).get("/broken?token=secret-query")
    assert response.status_code == 500
    assert response.json() == {"code": 500, "message": "服务器内部错误", "data": {}}
    assert UUID(response.headers["x-request-id"])
    logged = records(caplog)
    assert len(logged) == 1
    assert logged[0]["business_code"] == 500
    assert {entry["type"] for entry in logged[0]["exceptions"]} == {"RuntimeError", "ValueError"}
    assert any(frame["function"] == "broken" for frame in logged[0]["exceptions"][0]["frames"])
    assert "secret" not in json.dumps(logged)
    assert current_request_id() is None


@pytest.mark.parametrize(
    "supplied",
    [None, "secret-token", "x" * 10000, str(uuid4())],
    ids=["missing", "invalid", "oversized", "valid"],
)
def test_request_identity_is_bounded_and_logs_only_route_template(caplog, supplied):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    response = TestClient(sample_app()).get(
        "/items/private-id?token=private-query",
        headers={"x-request-id": supplied} if supplied else {},
    )
    request_id = response.headers["x-request-id"]
    assert UUID(request_id)
    if supplied and len(supplied) == 36:
        assert request_id == supplied
    assert response.json()["request_id"] == request_id
    logged = records(caplog)
    assert len(logged) == 1
    assert logged[0]["route"] == "/items/{item_id}"
    assert logged[0]["request_id"] == request_id
    assert "private-" not in json.dumps(logged)
    assert current_request_id() is None


@pytest.mark.asyncio
async def test_concurrent_context_is_isolated_and_reset():
    ids = [str(uuid4()), str(uuid4())]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=sample_app()), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            *(client.get("/items/1", headers={"x-request-id": identity}) for identity in ids)
        )
    assert [response.json()["request_id"] for response in responses] == ids
    assert current_request_id() is None


def test_successful_polling_is_debug_and_unknown_route_is_not_logged(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    client = TestClient(sample_app())
    assert client.post("/internal/ai-worker/tasks/claim").status_code == 200
    assert records(caplog) == []
    assert client.get("/secret-path?password=secret").status_code == 404
    assert records(caplog)[0]["route"] == "<unmatched>"
    assert "secret" not in json.dumps(records(caplog))


def test_stream_failure_terminates_without_exposing_original_exception(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    with pytest.raises(ResponseAborted) as error:
        TestClient(sample_app()).get("/stream")
    rendered = "".join(traceback.format_exception(error.value))
    assert "secret streaming message" not in rendered
    logged = records(caplog)
    assert len(logged) == 1
    assert logged[0]["status"] == 200
    assert logged[0]["exceptions"]
    assert "secret" not in json.dumps(logged)
    assert current_request_id() is None


def test_application_business_and_validation_errors_keep_contract(caplog):
    from testing_agent.app import create_app
    from testing_agent.core.errors import AppError

    app = create_app()

    @app.get("/diagnostic-business")
    async def business():
        raise AppError(1234, "expected denial", 403)

    @app.get("/diagnostic-validation")
    async def validation(count: int):
        return count

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    client = TestClient(app)
    denied = client.get("/diagnostic-business")
    invalid = client.get("/diagnostic-validation", params={"count": "bad"})
    assert denied.status_code == 403
    assert denied.json()["code"] == 1234
    assert invalid.status_code == 400
    assert invalid.json()["code"] == 400
    assert [item["business_code"] for item in records(caplog)] == [1234, 400]
    assert all("exceptions" not in item for item in records(caplog))
    assert all("x-request-id" in response.headers for response in (denied, invalid))


def test_duplicate_request_identity_is_replaced():
    value = str(uuid4())
    response = TestClient(sample_app()).get(
        "/items/1", headers=[("x-request-id", value), ("x-request-id", value)]
    )
    assert UUID(response.headers["x-request-id"])
    assert response.headers["x-request-id"] != value


def test_nested_router_templates_keep_prefixes_and_polling_level(caplog):
    app = FastAPI()
    app.add_middleware(RequestDiagnosticsMiddleware)
    internal = APIRouter(prefix="/internal")
    worker = APIRouter(prefix="/ai-worker")

    @worker.post("/tasks/{task_id}/heartbeat")
    async def heartbeat(task_id: str):
        return {}

    @worker.get("/tasks/{task_id}/snapshot")
    async def snapshot(task_id: str):
        raise RuntimeError("sensitive remote error")

    internal.include_router(worker)
    app.include_router(internal)
    client = TestClient(app)
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    assert client.post("/internal/ai-worker/tasks/private-task/heartbeat").status_code == 200
    assert client.get("/internal/ai-worker/tasks/private-task/snapshot").status_code == 500
    logged = records(caplog)
    assert [item["route"] for item in logged] == [
        "/internal/ai-worker/tasks/{task_id}/heartbeat",
        "/internal/ai-worker/tasks/{task_id}/snapshot",
    ]
    assert [record.levelno for record in caplog.records if record.name == LOGGER_NAME] == [
        logging.DEBUG,
        logging.ERROR,
    ]
    assert "private-task" not in json.dumps(logged)
    assert "sensitive remote error" not in json.dumps(logged)


def test_official_startup_uses_safe_logger_and_disables_raw_access_logs(monkeypatch):
    from copy import deepcopy

    from uvicorn.config import LOGGING_CONFIG

    from testing_agent import main

    original = deepcopy(LOGGING_CONFIG)
    settings = SimpleNamespace(http_host="127.0.0.1", http_port=8000, env="test")
    monkeypatch.setattr("sys.argv", ["control-plane"])
    monkeypatch.setattr(main, "load_settings", lambda path: settings)
    monkeypatch.setattr(main, "seed_super_admin", AsyncMock())
    runner = Mock()
    monkeypatch.setattr(main.uvicorn, "run", runner)
    # main sets APP_CONF; have pytest restore it after exercising the real entry point.
    monkeypatch.setenv("APP_CONF", "test")
    main.main()
    options = runner.call_args.kwargs
    assert options["access_log"] is False
    assert options["log_config"]["loggers"][LOGGER_NAME] == {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    assert LOGGING_CONFIG == original
