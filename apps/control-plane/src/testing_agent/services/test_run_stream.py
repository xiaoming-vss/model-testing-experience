"""Authorize and transport long-lived test-run streams without holding a session."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import suppress

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from testing_agent.core.errors import ErrForbidden
from testing_agent.db.session import AsyncSessionLocal
from testing_agent.repositories.api_case import ApiCaseRepository
from testing_agent.repositories.auth_session import AuthSessionRepository
from testing_agent.repositories.ui_test_case_run import UiTestCaseRunRepository
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.auth_session import SessionService
from testing_agent.services.ui_test_case_run import UiTestCaseRunService


async def authorize_run_subscription(
    kind: str,
    run_id: str,
    user_id: str,
    api_cases: ApiCaseService,
    api_collections: ApiCollectionRunService,
    ui_runs: UiTestCaseRunService,
) -> None:
    """Check the current user may observe this run before subscribing to events."""
    if kind == "api-case":
        await api_cases.get_run(user_id, run_id)
        api_run = await api_cases.repository.get_run(run_id)
        if api_run is None or api_run.trigger_user_id != user_id:
            raise ErrForbidden()
    elif kind == "api-collection":
        await api_collections.get(user_id, run_id)
    elif kind == "ui-case":
        await ui_runs.get_case_run(user_id, run_id)
        ui_run = await ui_runs.repository.get_case_run(run_id)
        if ui_run is None or ui_run.trigger_user_id != user_id:
            raise ErrForbidden()
    else:
        await ui_runs.get_suite_run(user_id, run_id)


async def stream_run_events(
    kind: str,
    run_id: str,
    request: Request,
    user_id: str,
    session,
    api_cases: ApiCaseService,
    api_collections: ApiCollectionRunService,
    ui_runs: UiTestCaseRunService,
) -> StreamingResponse:
    """Authorize, release the request transaction and stream committed changes."""
    await authorize_run_subscription(kind, run_id, user_id, api_cases, api_collections, ui_runs)

    # Streaming responses can outlive a request by a minute; do not hold a DB
    # connection or a transaction while waiting for Redis events.
    await session.rollback()
    url = request.app.state.settings.test_run_redis_url
    if not url:
        raise HTTPException(status_code=503, detail="Realtime notifications unavailable")
    client = Redis.from_url(url, socket_connect_timeout=1, socket_timeout=12)
    pubsub = client.pubsub()
    domain = "api" if kind.startswith("api-") else "ui"
    try:
        await pubsub.subscribe(f"mtx:api-ui:run:{domain}:{run_id}")
        ack = await pubsub.get_message(ignore_subscribe_messages=False, timeout=3)
        if not ack or ack.get("type") != "subscribe":
            raise TimeoutError("Redis subscription was not acknowledged")
    except (RedisError, OSError, TimeoutError):
        with suppress(RedisError, OSError, TimeoutError):
            await pubsub.aclose()
            await client.aclose()
        raise HTTPException(status_code=503, detail="Realtime notifications unavailable") from None

    async def events() -> AsyncIterator[str]:
        # Reconnect regularly to recheck session and project permissions.
        deadline = time.monotonic() + 60
        try:
            yield "event: ready\ndata: {}\n\n"
            while time.monotonic() < deadline and not await request.is_disconnected():
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10)
                if message:
                    yield "event: changed\ndata: {}\n\n"
                else:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(0.05)
        except (RedisError, OSError, TimeoutError):
            # Ending the stream causes the client to reconnect and reload.
            return
        finally:
            with suppress(RedisError, OSError, TimeoutError):
                await pubsub.aclose()
                await client.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


async def reauthorize_debug_stream(
    request: Request, user_id: str, domain: str, case_id: str
) -> None:
    """Recheck login, project and execute permission on a long-lived debug stream."""
    authorization = request.headers.get("authorization") or ""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401)
    async with AsyncSessionLocal() as session:
        actor = await SessionService(
            AuthSessionRepository(session), request.app.state.settings
        ).authenticate(token, method="POST", path=request.url.path)
        if actor != user_id:
            raise HTTPException(status_code=403)
        if domain == "api":
            await ApiCaseService(ApiCaseRepository(session)).get_accessible_context(
                actor, case_id, action="execute"
            )
        else:
            await UiTestCaseRunService(UiTestCaseRunRepository(session)).get_accessible_case(
                actor, case_id, action="execute"
            )
