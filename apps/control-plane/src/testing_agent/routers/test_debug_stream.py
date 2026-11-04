"""Subscribe before submitting a single-case debug run to avoid a completion race."""

import asyncio
import base64
import hashlib
import json
import re
import time
from collections.abc import AsyncIterator
from contextlib import suppress

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from testing_agent.api.deps import (
    get_api_case_service,
    get_current_user_id,
    get_session,
    get_ui_test_case_run_service,
)
from testing_agent.core.sid import new_id
from testing_agent.schemas.api_run import RunApiCaseRequest
from testing_agent.schemas.ui_run import DebugRunUiCaseRequest
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.live_debug_transfer import (
    CHUNK_BYTES,
    CLIENT_STALL_SECONDS,
    HEARTBEAT_INTERVAL_SECONDS,
)
from testing_agent.services.test_run_stream import reauthorize_debug_stream
from testing_agent.services.ui_test_case_run import UiTestCaseRunService

router = APIRouter()


async def _stream_ui_artifacts(request, client, delivery, reauthorize=None):
    """Stream private objects with SSE backpressure; acknowledge only complete files."""
    from testing_agent.core.object_storage import ObjectStorage

    delivery_id = delivery.get("deliveryId", "")
    files = delivery.get("files")
    if not isinstance(delivery_id, str) or not re.fullmatch(r"[0-9a-f]{32}", delivery_id):
        return
    if not isinstance(files, list):
        return
    ack_channel = f"mtx:api-ui:delivery:{delivery_id}"
    failures = []
    done = False
    stalled = asyncio.Event()
    last_progress = time.monotonic()

    async def heartbeat():
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            if time.monotonic() - last_progress >= CLIENT_STALL_SECONDS:
                stalled.set()
                await client.publish(ack_channel, '{"event":"gone"}')
                return
            await client.publish(ack_channel, '{"event":"heartbeat"}')

    pulse = asyncio.create_task(heartbeat())
    try:
        if reauthorize is not None:
            await reauthorize()
        if stalled.is_set():
            return
        next_auth = time.monotonic() + 60
        try:
            storage = await asyncio.to_thread(ObjectStorage, request.app.state.settings.s3)
        except (BotoCoreError, ClientError, OSError, ValueError):
            failures = [file.get("path", "") for file in files if isinstance(file, dict)]
            await client.publish(ack_channel, json.dumps({"event": "done", "failed": failures}))
            done = True
            return
        if stalled.is_set():
            return
        for file in files:
            if not isinstance(file, dict):
                continue
            path = file.get("path", "")
            media = file.get("media", "")
            if (
                not isinstance(path, str)
                or not re.fullmatch(r"/v1/files/[a-zA-Z0-9-]+/download", path)
                or media not in {"image/png", "application/zip"}
            ):
                failures.append(path)
                continue
            body = None
            try:
                response = await asyncio.to_thread(
                    storage.client.get_object, Bucket=file["bucket"], Key=file["key"]
                )
                body = response["Body"]
                digest, size, part, carry = hashlib.sha256(), 0, 0, b""
                while True:
                    data = await asyncio.to_thread(body.read, CHUNK_BYTES)
                    if not data:
                        break
                    digest.update(data)
                    size += len(data)
                    data = carry + data
                    boundary = len(data) - len(data) % 3
                    carry, data = data[boundary:], data[:boundary]
                    if data:
                        if stalled.is_set():
                            return
                        if reauthorize is not None and time.monotonic() >= next_auth:
                            await reauthorize()
                            next_auth = time.monotonic() + 60
                        encoded = base64.b64encode(data).decode("ascii")
                        last_progress = time.monotonic()
                        yield (
                            "event: artifact\ndata: "
                            + json.dumps(
                                {"path": path, "media": media, "part": part, "data": encoded}
                            )
                            + "\n\n"
                        )
                        if stalled.is_set():
                            return
                        part += 1
                if carry or not part:
                    if stalled.is_set():
                        return
                    last_progress = time.monotonic()
                    yield (
                        "event: artifact\ndata: "
                        + json.dumps(
                            {
                                "path": path,
                                "media": media,
                                "part": part,
                                "data": base64.b64encode(carry).decode("ascii"),
                            }
                        )
                        + "\n\n"
                    )
                    if stalled.is_set():
                        return
                if size != file.get("size") or digest.hexdigest() != file.get("sha256"):
                    failures.append(path)
            except (BotoCoreError, ClientError, RedisError, OSError, KeyError, ValueError):
                failures.append(path)
            finally:
                if body is not None:
                    await asyncio.to_thread(body.close)
        await client.publish(ack_channel, json.dumps({"event": "done", "failed": failures}))
        done = True
    finally:
        pulse.cancel()
        with suppress(asyncio.CancelledError, RedisError, OSError, TimeoutError):
            await pulse
        if not done:
            with suppress(RedisError, OSError, TimeoutError):
                await client.publish(ack_channel, '{"event":"gone"}')


async def _start_stream(
    request: Request, domain: str, run_id: str, submit, session, reauthorize=None
):
    url = request.app.state.settings.test_run_redis_url
    if not url:
        raise HTTPException(status_code=503, detail="Realtime notifications unavailable")
    client = Redis.from_url(url, socket_connect_timeout=1, socket_timeout=120)
    pubsub = client.pubsub()
    try:
        # The listener exists before the task becomes visible to a Worker.
        await pubsub.subscribe(f"mtx:api-ui:run:{domain}:{run_id}")
        ack = await pubsub.get_message(ignore_subscribe_messages=False, timeout=3)
        if not ack or ack.get("type") != "subscribe":
            raise TimeoutError("Redis subscription was not acknowledged")
    except (RedisError, OSError, TimeoutError):
        with suppress(RedisError, OSError, TimeoutError):
            await pubsub.aclose()
            await client.aclose()
        raise HTTPException(status_code=503, detail="Realtime notifications unavailable") from None
    try:
        initial = await submit()
        await session.rollback()  # release the DB connection before streaming
    except BaseException:
        with suppress(RedisError, OSError, TimeoutError):
            await pubsub.aclose()
            await client.aclose()
        raise

    async def events() -> AsyncIterator[str]:
        try:
            next_auth = time.monotonic() + 60
            yield "event: started\ndata: " + json.dumps(initial, ensure_ascii=False) + "\n\n"
            while not await request.is_disconnected():
                if reauthorize is not None and time.monotonic() >= next_auth:
                    await reauthorize()
                    next_auth = time.monotonic() + 60
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10)
                if message:
                    data = message.get("data")
                    try:
                        payload = json.loads(data)
                    except (TypeError, ValueError):
                        yield "event: changed\ndata: {}\n\n"
                        continue
                    event_type = payload.get("event")
                    if event_type in {"finished", "artifacts_ready", "execution_finished"}:
                        if (
                            event_type in {"finished", "execution_finished"}
                            and reauthorize is not None
                        ):
                            await reauthorize()
                        cipher = IntegrationCredentialCipher(
                            request.app.state.settings.integration_key
                        )
                        plaintext = await asyncio.to_thread(
                            cipher.decrypt, payload.get("ciphertext", "")
                        )
                        final = await asyncio.to_thread(json.loads, plaintext)
                        if final.get("domain") != domain or final.get("runId") != run_id:
                            continue
                        if payload.get("event") == "execution_finished" and domain == "ui":
                            yield (
                                "event: execution_finished\ndata: "
                                + json.dumps(final.get("result"))
                                + "\n\n"
                            )
                            continue
                        if payload.get("event") == "artifacts_ready" and domain == "ui":
                            async for frame in _stream_ui_artifacts(
                                request, client, final, reauthorize
                            ):
                                yield frame
                            continue
                        if payload.get("event") != "finished":
                            continue
                        encoded = await asyncio.to_thread(
                            json.dumps, final.get("result"), ensure_ascii=False
                        )
                        yield "event: finished\ndata: " + encoded + "\n\n"
                        return
                else:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(0.05)
        except Exception:
            # Connection loss, expired login, and revoked permissions all close the stream.
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


@router.post("/test-debug-stream/api-case/{case_id}", response_class=StreamingResponse)
async def api_debug_stream(
    case_id: str,
    body: RunApiCaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
    service: ApiCaseService = Depends(get_api_case_service),
):
    run_id = new_id()
    return await _start_stream(
        request,
        "api",
        run_id,
        lambda: service.run(user_id, case_id, body, run_id=run_id, live_debug=True),
        session,
        lambda: reauthorize_debug_stream(request, user_id, "api", case_id),
    )


@router.post("/test-debug-stream/ui-case/{case_id}", response_class=StreamingResponse)
async def ui_debug_stream(
    case_id: str,
    body: DebugRunUiCaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
    service: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    run_id = new_id()
    return await _start_stream(
        request,
        "ui",
        run_id,
        lambda: service.debug_run_case(user_id, case_id, body, run_id=run_id, live_debug=True),
        session,
        lambda: reauthorize_debug_stream(request, user_id, "ui", case_id),
    )
