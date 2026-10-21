import asyncio
import io
import threading
from dataclasses import replace

import pytest
from starlette.datastructures import UploadFile

from testing_agent.core.config import Settings
from testing_agent.core.errors import AppError
from testing_agent.core.import_limits import ImportLimits
from testing_agent.services import import_budget
from testing_agent.services.import_budget import parse_bounded, read_bounded


@pytest.mark.parametrize(
    ("payload", "limits", "status"),
    [
        (b"\xff", ImportLimits(), 400),
        ("cases: [", ImportLimits(), 400),
        ("cases: &cases [*cases]", ImportLimits(), 400),
        ("cases: [[[[[1]]]]]", ImportLimits(max_depth=4), 413),
        ("cases: [1, 2, 3]", ImportLimits(max_items=2), 413),
        ({"cases": [1, 2, 3]}, ImportLimits(max_items=2), 413),
        ({"cases": [{"title": "long"}]}, ImportLimits(max_field_chars=3), 413),
        ("cases: [1, 2, 3]", ImportLimits(max_nodes=3), 413),
        ("cases: []", ImportLimits(max_bytes=4), 413),
    ],
)
def test_invalid_or_excessive_inputs_are_explicit(payload, limits, status):
    with pytest.raises(AppError) as error:
        parse_bounded(payload, limits)
    assert error.value.http_code == status


def test_rejects_cycles_in_direct_payload():
    value = []
    value.append(value)
    with pytest.raises(AppError, match="循环引用"):
        parse_bounded(value, ImportLimits())


@pytest.mark.asyncio
async def test_bounded_read_checks_actual_bytes_without_size_metadata():
    source = io.BytesIO(b"x" * 200)
    with pytest.raises(AppError) as error:
        await read_bounded(None, UploadFile(source), ImportLimits(max_bytes=64))
    assert error.value.http_code == 413
    assert source.tell() == 65


@pytest.mark.asyncio
async def test_bom_and_root_list_keep_legacy_envelope():
    result = await read_bounded(
        None, UploadFile(io.BytesIO(b"\xef\xbb\xbf- title: ok")), ImportLimits()
    )
    assert result == {"items": [{"title": "ok"}]}


@pytest.mark.asyncio
async def test_cancellation_does_not_free_running_parser_capacity(monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    original = import_budget.parse_bounded

    def slow(payload, limits):
        entered.set()
        assert finish.wait(5)
        return original(payload, limits)

    monkeypatch.setattr(import_budget, "parse_bounded", slow)
    limits = ImportLimits(max_concurrent=1)
    task = asyncio.create_task(read_bounded("cases: []", None, limits))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(AppError) as error:
            await read_bounded("cases: []", None, limits)
        assert error.value.http_code == 429
        # The event loop can run while the parser is deliberately blocked.
        await asyncio.wait_for(asyncio.sleep(0.001), 0.5)
    finally:
        finish.set()
    for _ in range(100):
        await asyncio.sleep(0.01)
        if import_budget._slots(1).acquire(blocking=False):
            import_budget._slots(1).release()
            break
    else:
        pytest.fail("Parser capacity was not returned")
    assert await read_bounded("cases: []", None, limits) == {"cases": []}


def test_configuration_round_trip_and_invalid_limits():
    assert Settings.from_mapping({"asset_import": {"max_items": 25}}).asset_import.max_items == 25
    for field in ImportLimits.__dataclass_fields__:
        with pytest.raises(ValueError):
            replace(ImportLimits(), **{field: 0})
        with pytest.raises(ValueError):
            replace(ImportLimits(), **{field: True})


@pytest.mark.asyncio
async def test_http_envelope_rejects_chunked_overflow_before_framework_parsing():
    from testing_agent.core.import_http import ImportEnvelopeMiddleware

    calls, responses = [], []

    async def app(scope, receive, send):
        calls.append(await receive())

    messages = iter(
        [
            {"type": "http.request", "body": b"x" * 65536, "more_body": True},
            {"type": "http.request", "body": b"y" * 65, "more_body": False},
        ]
    )

    async def receive():
        return next(messages)

    async def send(message):
        responses.append(message)

    middleware = ImportEnvelopeMiddleware(app, ImportLimits(max_bytes=64))
    await middleware(
        {"type": "http", "method": "POST", "path": "/v1/api-collections/a/import"},
        receive,
        send,
    )
    assert not calls
    assert responses[0]["status"] == 413
    assert middleware.active == 0


@pytest.mark.asyncio
async def test_http_envelope_replays_body_and_does_not_affect_other_routes():
    from testing_agent.core.import_http import ImportEnvelopeMiddleware

    seen = []

    async def app(scope, receive, send):
        seen.append((await receive())["body"])

    async def receive():
        return {"type": "http.request", "body": b'{"cases": []}', "more_body": False}

    async def send(message):
        pass

    middleware = ImportEnvelopeMiddleware(app, ImportLimits())
    for path in ("/v1/ui-test-suites/a/import", "/internal/ai/tasks/claim"):
        await middleware({"type": "http", "method": "POST", "path": path}, receive, send)
    assert seen == [b'{"cases": []}'] * 2
    assert middleware.active == 0
