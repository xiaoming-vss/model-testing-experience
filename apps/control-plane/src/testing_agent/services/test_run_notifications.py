"""Best-effort notifications; the committed task queue remains authoritative."""

import asyncio
import logging
from contextlib import suppress
from weakref import WeakKeyDictionary

from redis.asyncio import Redis
from redis.exceptions import RedisError

from testing_agent.core.config import get_settings

logger = logging.getLogger(__name__)
TASK_CHANNEL = "mtx:api-ui:tasks"
TASK_WAKE_QUEUE = "mtx:api-ui:task-wakeups"
_clients: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple[str, float], Redis]] = (
    WeakKeyDictionary()
)


def _notification_client(url: str, timeout: float) -> Redis:
    """Reuse a per-event-loop connection pool without sharing clients across loops."""
    loop = asyncio.get_running_loop()
    clients = _clients.setdefault(loop, {})
    key = (url, timeout)
    if key not in clients:
        clients[key] = Redis.from_url(url, socket_connect_timeout=1, socket_timeout=timeout)
    return clients[key]


async def close_notification_clients() -> None:
    """Close this process's notification pools during application shutdown."""
    clients = _clients.pop(asyncio.get_running_loop(), {})
    for client in clients.values():
        with suppress(RedisError, OSError, TimeoutError):
            await client.aclose()


async def _publish(channel: str, message: str, *, timeout: float = 1) -> None:
    url = get_settings().test_run_redis_url
    if not url:
        return
    client = _notification_client(url, timeout)
    try:
        await client.publish(channel, message)
    except (RedisError, OSError, TimeoutError):
        # The worker's periodic queue check is the durable fallback. Do not log
        # exception text: Redis connection strings can contain credentials.
        logger.warning("Test task notification unavailable; workers will use fallback polling")


async def notify_task_available() -> None:
    """Wake one new Worker, and retain broadcast compatibility with old Workers."""
    url = get_settings().test_run_redis_url
    if not url:
        return
    client = _notification_client(url, 1)
    try:
        async with client.pipeline(transaction=True) as pipe:
            # Tokens are hints, not tasks. Cap accumulation while Workers are offline.
            pipe.lpush(TASK_WAKE_QUEUE, "available")
            pipe.ltrim(TASK_WAKE_QUEUE, 0, 9999)
            pipe.expire(TASK_WAKE_QUEUE, 60)
            # New Workers ignore this version; old subscribers wake as before.
            pipe.publish(TASK_CHANNEL, "available-v2")
            await pipe.execute()
    except (RedisError, OSError, TimeoutError):
        logger.warning("Test task notification unavailable; workers will use fallback polling")


async def notify_run_changed(domain: str, run_id: str) -> None:
    """Notify subscribers to reload a committed API/UI run."""
    if domain in {"api", "ui"} and run_id:
        await _publish(f"mtx:api-ui:run:{domain}:{run_id}", "changed")


async def notify_task_control(task_id: str) -> None:
    """Wake a worker so it can recheck the authoritative stop state."""
    await _publish(f"mtx:api-ui:control:{task_id}", "check")


async def notify_run_finished(domain: str, run_id: str, result: dict) -> None:
    """Deliver a transient debug result to an already subscribed page."""
    import asyncio
    import json

    from testing_agent.services.integration_credentials import IntegrationCredentialCipher

    if domain in {"api", "ui"} and run_id:
        cipher = IntegrationCredentialCipher(get_settings().integration_key)
        plaintext = await asyncio.to_thread(
            json.dumps, {"domain": domain, "runId": run_id, "result": result}, ensure_ascii=False
        )
        encrypted = await asyncio.to_thread(cipher.encrypt, plaintext)
        await _publish(
            f"mtx:api-ui:run:{domain}:{run_id}",
            json.dumps({"event": "finished", "ciphertext": encrypted}),
            timeout=60,
        )


async def notify_ui_debug_execution_finished(run_id: str, status: str) -> None:
    """Publish the committed outcome before potentially slow artifact delivery."""
    import json

    from testing_agent.services.integration_credentials import IntegrationCredentialCipher

    if not run_id or status not in {"success", "failed", "error", "canceled"}:
        return
    plaintext = json.dumps({"domain": "ui", "runId": run_id, "result": {"status": status}})
    encrypted = await asyncio.to_thread(
        IntegrationCredentialCipher(get_settings().integration_key).encrypt, plaintext
    )
    await _publish(
        f"mtx:api-ui:run:ui:{run_id}",
        json.dumps({"event": "execution_finished", "ciphertext": encrypted}),
    )


async def has_run_subscribers(domain: str, run_id: str) -> bool:
    """Avoid loading ephemeral artifacts when nobody can receive them."""
    url = get_settings().test_run_redis_url
    if not url or domain not in {"api", "ui"} or not run_id:
        return False
    client = _notification_client(url, 1)
    try:
        counts = await client.pubsub_numsub(f"mtx:api-ui:run:{domain}:{run_id}")
        return bool(counts and counts[0][1])
    except (RedisError, OSError, TimeoutError):
        return False
