"""Wake idle workers on best-effort Redis notifications."""

import asyncio
import random
from contextlib import suppress

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..core import logger

TASK_CHANNEL = "mtx:api-ui:tasks"
TASK_WAKE_QUEUE = "mtx:api-ui:task-wakeups"


def _reconnect_delay() -> float:
    """Spread reconnects after an outage while keeping the average at three seconds."""
    return random.uniform(2.0, 4.0)


async def listen_for_tasks(
    url: str, wake: asyncio.Event, channel: str = TASK_CHANNEL
) -> None:
    """Reconnect until cancelled; wake after subscription to cover missed messages."""
    while True:
        client = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=5)
        try:
            async with client.pubsub() as pubsub:
                await pubsub.subscribe(channel)
                ack = await pubsub.get_message(
                    ignore_subscribe_messages=False, timeout=3
                )
                if not ack or ack.get("type") != "subscribe":
                    raise TimeoutError("Redis subscription was not acknowledged")
                wake.set()
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if message is not None:
                        if channel != TASK_CHANNEL or message.get("data") not in (
                            b"available-v2",
                            "available-v2",
                        ):
                            wake.set()
                    else:
                        await asyncio.sleep(0.05)
        except (RedisError, OSError, TimeoutError):
            # Never log the exception text, which may include connection secrets.
            logger.warn("task notifications unavailable; retrying")
            await asyncio.sleep(_reconnect_delay())
        finally:
            with suppress(RedisError, OSError, TimeoutError):
                await client.aclose()


async def wait_for_task(url: str, wake: asyncio.Event, timeout: float) -> None:
    """Wait for one shared hint, an old-server broadcast, or the durable fallback."""
    if not url:
        try:
            await asyncio.wait_for(wake.wait(), timeout=timeout)
        except TimeoutError:
            pass
        return
    client = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=timeout + 2)
    pop = asyncio.create_task(client.brpop(TASK_WAKE_QUEUE, timeout=timeout))
    broadcast = asyncio.create_task(wake.wait())
    try:
        done, _ = await asyncio.wait(
            (pop, broadcast), timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if pop in done:
            await pop
    except (RedisError, OSError, TimeoutError):
        # Avoid a tight retry loop while Redis is unavailable.
        try:
            await asyncio.wait_for(wake.wait(), timeout=timeout)
        except TimeoutError:
            pass
    finally:
        for task in (pop, broadcast):
            task.cancel()
            with suppress(asyncio.CancelledError, RedisError, OSError, TimeoutError):
                await task
        with suppress(RedisError, OSError, TimeoutError):
            await client.aclose()


async def publish_worker_presence(
    url: str, worker_id: str, busy: asyncio.Event, refresh: asyncio.Event
) -> None:
    """Publish expiring availability without making presence authoritative for claims."""
    key = f"mtx:api-ui:workers:{worker_id}"
    while True:
        client = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        try:
            while True:
                refresh.clear()
                await client.set(key, "busy" if busy.is_set() else "idle", ex=35)
                try:
                    await asyncio.wait_for(refresh.wait(), timeout=10)
                except TimeoutError:
                    pass
        except (RedisError, OSError, TimeoutError):
            logger.warn("worker presence unavailable; retrying")
            await asyncio.sleep(_reconnect_delay())
        finally:
            with suppress(RedisError, OSError, TimeoutError):
                await client.aclose()
