"""Authenticated, short-lived subscriptions to committed test run changes."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from testing_agent.api.deps import (
    get_api_case_service,
    get_api_collection_run_service,
    get_current_user_id,
    get_session,
    get_ui_test_case_run_service,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.common import ApiResponse, StatusData
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.test_run_stop import stop_run
from testing_agent.services.test_run_stream import authorize_run_subscription
from testing_agent.services.ui_test_case_run import UiTestCaseRunService

router = APIRouter()
RunKind = Literal["api-case", "api-collection", "ui-case", "ui-suite"]


@router.get("/test-run-events/{kind}/{run_id}", response_class=StreamingResponse)
async def test_run_events(
    kind: RunKind,
    run_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
    api_cases: ApiCaseService = Depends(get_api_case_service),
    api_collections: ApiCollectionRunService = Depends(get_api_collection_run_service),
    ui_runs: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
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


@router.post("/test-runs/{kind}/{run_id}/stop", response_model=ApiResponse[StatusData])
async def stop_test_run(
    kind: RunKind,
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
    api_cases: ApiCaseService = Depends(get_api_case_service),
    api_collections: ApiCollectionRunService = Depends(get_api_collection_run_service),
    ui_runs: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    return success_payload(
        await stop_run(kind, run_id, user_id, session, api_cases, api_collections, ui_runs)
    )
