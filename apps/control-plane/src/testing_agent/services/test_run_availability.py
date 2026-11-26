"""Approximate queue availability, independent of authoritative task dispatch."""

from contextlib import suppress

from redis.asyncio import Redis
from redis.exceptions import RedisError

from testing_agent.schemas.test_run import RunAvailabilityState


class TestRunAvailabilityService:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url

    async def state(self) -> RunAvailabilityState:
        if not self.redis_url:
            return "unknown"
        client = Redis.from_url(self.redis_url, socket_connect_timeout=1, socket_timeout=1)
        try:
            keys = []
            async for key in client.scan_iter(match="mtx:api-ui:workers:*", count=200):
                keys.append(key)
                if len(keys) >= 1000:
                    break
            if not keys:
                return "offline"
            states = await client.mget(keys)
            if any(state in {b"idle", "idle"} for state in states):
                return "available"
            if any(state in {b"busy", "busy"} for state in states):
                return "busy"
            return "unknown"
        except (RedisError, OSError, TimeoutError):
            return "unknown"
        finally:
            with suppress(RedisError, OSError, TimeoutError):
                await client.aclose()
