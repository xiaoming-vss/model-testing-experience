"""Coordinate bounded, private delivery of ephemeral UI debug artifacts."""

import asyncio
import json
import uuid
from contextlib import suppress
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from testing_agent.core.config import get_settings
from testing_agent.services.integration_credentials import IntegrationCredentialCipher

CHUNK_BYTES = 192 * 1024  # divisible by three so base64 chunks can be concatenated
ACK_TIMEOUT_SECONDS = 20
SUBSCRIBER_CHECK_SECONDS = 2
HEARTBEAT_INTERVAL_SECONDS = 5
CLIENT_STALL_SECONDS = 30


async def request_ui_artifact_delivery(run_id: str, files: list[dict[str, Any]]) -> set[str]:
    """Ask the subscribed control plane to stream S3 objects, and await its receipt.

    Redis carries only encrypted object metadata and small acknowledgements; file bytes
    move directly from object storage to the authenticated SSE connection. A random
    per-delivery acknowledgement channel cannot be guessed from a run identifier.
    """
    settings = get_settings()
    failed = {str(file["path"]) for file in files}
    if not settings.test_run_redis_url or not files:
        return failed
    delivery_id = uuid.uuid4().hex
    ack_channel = f"mtx:api-ui:delivery:{delivery_id}"
    client = Redis.from_url(
        settings.test_run_redis_url, socket_connect_timeout=1, socket_timeout=30
    )
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(ack_channel)
        ack = await pubsub.get_message(ignore_subscribe_messages=False, timeout=3)
        if not ack or ack.get("type") != "subscribe":
            return failed
        message = {
            "domain": "ui",
            "runId": run_id,
            "deliveryId": delivery_id,
            "files": files,
        }
        plaintext = json.dumps(message, ensure_ascii=False)
        ciphertext = await asyncio.to_thread(
            IntegrationCredentialCipher(settings.integration_key).encrypt, plaintext
        )
        subscribers = await client.publish(
            f"mtx:api-ui:run:ui:{run_id}",
            json.dumps({"event": "artifacts_ready", "ciphertext": ciphertext}),
        )
        if not subscribers:
            return failed
        deadline = asyncio.get_running_loop().time() + ACK_TIMEOUT_SECONDS
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return failed
            response = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=min(SUBSCRIBER_CHECK_SECONDS, remaining)
            )
            if not response:
                counts = await client.pubsub_numsub(f"mtx:api-ui:run:ui:{run_id}")
                if not counts or not counts[0][1]:
                    return failed
                continue
            try:
                data = json.loads(response.get("data"))
            except (TypeError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            if data.get("event") == "heartbeat":
                deadline = asyncio.get_running_loop().time() + ACK_TIMEOUT_SECONDS
                continue
            if data.get("event") == "done":
                missing = data.get("failed", [])
                if isinstance(missing, list):
                    return failed.intersection(path for path in missing if isinstance(path, str))
                return failed
            return failed
    except (RedisError, OSError, TimeoutError, ValueError):
        return failed
    finally:
        with suppress(RedisError, OSError, TimeoutError):
            await pubsub.aclose()
            await client.aclose()
