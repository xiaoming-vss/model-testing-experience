"""Approximate queue availability, independent of authoritative task dispatch."""

from contextlib import suppress

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from testing_agent.api.deps import get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.common import ApiResponse

router = APIRouter()


class AvailabilityResponse(BaseModel):
    state: str


@router.get("/test-run-availability", response_model=ApiResponse[AvailabilityResponse])
async def availability(request: Request, user_id: str = Depends(get_current_user_id)):
    del user_id
    url = request.app.state.settings.test_run_redis_url
    if not url:
        return success_payload({"state": "unknown"})
    client = Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
    try:
        keys = []
        async for key in client.scan_iter(match="mtx:api-ui:workers:*", count=200):
            keys.append(key)
            if len(keys) >= 1000:
                break
        if not keys:
            return success_payload({"state": "offline"})
        states = await client.mget(keys)
        if any(state in {b"idle", "idle"} for state in states):
            return success_payload({"state": "available"})
        if any(state in {b"busy", "busy"} for state in states):
            return success_payload({"state": "busy"})
        return success_payload({"state": "unknown"})
    except (RedisError, OSError, TimeoutError):
        return success_payload({"state": "unknown"})
    finally:
        with suppress(RedisError, OSError, TimeoutError):
            await client.aclose()
