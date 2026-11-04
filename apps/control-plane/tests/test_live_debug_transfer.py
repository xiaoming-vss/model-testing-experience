import asyncio
import base64
import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from testing_agent.routers.test_debug_stream import _stream_ui_artifacts
from testing_agent.services.live_debug_transfer import CHUNK_BYTES


class Client:
    def __init__(self):
        self.messages = []

    async def publish(self, channel, message):
        self.messages.append((channel, json.loads(message)))


@pytest.mark.asyncio
async def test_producer_encrypts_manifest_and_waits_for_delivery_receipt(monkeypatch):
    from testing_agent.services import live_debug_transfer
    from testing_agent.services.integration_credentials import IntegrationCredentialCipher

    class PubSub:
        def __init__(self):
            self.responses = iter(
                [
                    {"type": "subscribe"},
                    {"data": b'{"event":"heartbeat"}'},
                    {"data": b'{"event":"done","failed":["/v1/files/b/download"]}'},
                ]
            )

        async def subscribe(self, channel):
            self.channel = channel

        async def get_message(self, **kwargs):
            return next(self.responses)

        async def aclose(self):
            pass

    class RedisClient:
        def __init__(self):
            self.subscription = PubSub()
            self.published = []

        def pubsub(self):
            return self.subscription

        async def publish(self, channel, payload):
            self.published.append((channel, json.loads(payload)))
            return 1

        async def aclose(self):
            pass

    client = RedisClient()
    settings = SimpleNamespace(test_run_redis_url="redis://test", integration_key="safe-test-key")
    monkeypatch.setattr(live_debug_transfer, "get_settings", lambda: settings)
    monkeypatch.setattr(live_debug_transfer.Redis, "from_url", lambda *a, **kw: client)
    files = [{"path": "/v1/files/a/download"}, {"path": "/v1/files/b/download"}]
    failures = await live_debug_transfer.request_ui_artifact_delivery("run", files)
    assert failures == {"/v1/files/b/download"}
    channel, message = client.published[0]
    assert channel == "mtx:api-ui:run:ui:run"
    assert message["event"] == "artifacts_ready"
    decrypted = json.loads(
        IntegrationCredentialCipher(settings.integration_key).decrypt(message["ciphertext"])
    )
    assert decrypted["files"] == files
    assert decrypted["runId"] == "run"
    assert client.subscription.channel.endswith(decrypted["deliveryId"])


@pytest.mark.asyncio
async def test_producer_stops_waiting_when_debug_subscriber_leaves(monkeypatch):
    from testing_agent.services import live_debug_transfer

    class PubSub:
        async def subscribe(self, channel):
            pass

        async def get_message(self, *, ignore_subscribe_messages, timeout):
            if not ignore_subscribe_messages:
                return {"type": "subscribe"}
            return None

        async def aclose(self):
            pass

    class RedisClient:
        def pubsub(self):
            return PubSub()

        async def publish(self, channel, payload):
            return 1

        async def pubsub_numsub(self, channel):
            assert channel == "mtx:api-ui:run:ui:run"
            return [(channel, 0)]

        async def aclose(self):
            pass

    settings = SimpleNamespace(test_run_redis_url="redis://test", integration_key="safe-test-key")
    monkeypatch.setattr(live_debug_transfer, "get_settings", lambda: settings)
    monkeypatch.setattr(live_debug_transfer.Redis, "from_url", lambda *a, **kw: RedisClient())
    files = [{"path": "/v1/files/a/download"}]
    assert await live_debug_transfer.request_ui_artifact_delivery("run", files) == {
        "/v1/files/a/download"
    }


@pytest.mark.asyncio
async def test_producer_continues_waiting_for_connected_debug_subscriber(monkeypatch):
    from testing_agent.services import live_debug_transfer

    class PubSub:
        def __init__(self):
            self.responses = iter([{"type": "subscribe"}, None, {"data": b'{"event":"done"}'}])

        async def subscribe(self, channel):
            pass

        async def get_message(self, **kwargs):
            return next(self.responses)

        async def aclose(self):
            pass

    class RedisClient:
        def pubsub(self):
            return PubSub()

        async def publish(self, channel, payload):
            return 1

        async def pubsub_numsub(self, channel):
            return [(channel, 1)]

        async def aclose(self):
            pass

    settings = SimpleNamespace(test_run_redis_url="redis://test", integration_key="safe-test-key")
    monkeypatch.setattr(live_debug_transfer, "get_settings", lambda: settings)
    monkeypatch.setattr(live_debug_transfer.Redis, "from_url", lambda *a, **kw: RedisClient())
    assert (
        await live_debug_transfer.request_ui_artifact_delivery(
            "run", [{"path": "/v1/files/a/download"}]
        )
        == set()
    )


@pytest.mark.asyncio
async def test_streams_verified_artifact_in_bounded_chunks_and_acknowledges(monkeypatch):
    from testing_agent.core import object_storage

    content = b"x" * (CHUNK_BYTES * 2 + 17)

    class Body(io.BytesIO):
        def read(self, size=-1):
            assert size == CHUNK_BYTES
            return super().read(min(size, 100001))  # partial reads need base64 carry

    body = Body(content)
    storage = SimpleNamespace(client=SimpleNamespace(get_object=lambda **kw: {"Body": body}))
    monkeypatch.setattr(object_storage, "ObjectStorage", lambda settings: storage)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(s3={})))
    )
    delivery = {
        "deliveryId": "a" * 32,
        "files": [
            {
                "path": "/v1/files/file-1/download",
                "media": "image/png",
                "bucket": "b",
                "key": "k",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }
    client = Client()
    frames = [frame async for frame in _stream_ui_artifacts(request, client, delivery)]
    chunks = [json.loads(frame.split("data: ", 1)[1]) for frame in frames]
    assert all(set(chunk) == {"path", "media", "part", "data"} for chunk in chunks)
    assert [c["part"] for c in chunks] == list(range(len(chunks)))
    assert base64.b64decode("".join(c["data"] for c in chunks)) == content
    assert body.closed
    assert client.messages[-1][1] == {"event": "done", "failed": []}


@pytest.mark.asyncio
async def test_disconnect_reports_failure_and_closes_object(monkeypatch):
    from testing_agent.core import object_storage

    class Body(io.BytesIO):
        reads = 0

        def read(self, size=-1):
            self.reads += 1
            return super().read(size)

    body = Body(b"a" * (CHUNK_BYTES * 2))
    storage = SimpleNamespace(client=SimpleNamespace(get_object=lambda **kw: {"Body": body}))
    monkeypatch.setattr(object_storage, "ObjectStorage", lambda settings: storage)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(s3={})))
    )
    delivery = {
        "deliveryId": "b" * 32,
        "files": [
            {"path": "/v1/files/f/download", "media": "application/zip", "bucket": "b", "key": "k"}
        ],
    }
    client = Client()
    stream = _stream_ui_artifacts(request, client, delivery)
    assert "event: artifact" in await anext(stream)
    await asyncio.sleep(0.05)
    assert body.reads == 1  # a slow client must not cause further storage reads
    await stream.aclose()
    assert body.closed
    assert client.messages[-1][1] == {"event": "gone"}


@pytest.mark.asyncio
async def test_stalled_client_releases_delivery_instead_of_holding_it_forever(monkeypatch):
    from testing_agent.core import object_storage
    from testing_agent.routers import test_debug_stream

    body = io.BytesIO(b"a" * (CHUNK_BYTES * 2))
    storage = SimpleNamespace(client=SimpleNamespace(get_object=lambda **kw: {"Body": body}))
    monkeypatch.setattr(object_storage, "ObjectStorage", lambda settings: storage)
    monkeypatch.setattr(test_debug_stream, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(test_debug_stream, "CLIENT_STALL_SECONDS", 0.03)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(s3={})))
    )
    delivery = {
        "deliveryId": "e" * 32,
        "files": [
            {"path": "/v1/files/f/download", "media": "application/zip", "bucket": "b", "key": "k"}
        ],
    }
    client = Client()
    stream = _stream_ui_artifacts(request, client, delivery)
    await anext(stream)
    await asyncio.sleep(0.08)
    assert any(message["event"] == "gone" for _, message in client.messages)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert body.closed


@pytest.mark.asyncio
async def test_checksum_mismatch_is_reported_to_sender(monkeypatch):
    from testing_agent.core import object_storage

    body = io.BytesIO(b"corrupted")
    storage = SimpleNamespace(client=SimpleNamespace(get_object=lambda **kw: {"Body": body}))
    monkeypatch.setattr(object_storage, "ObjectStorage", lambda settings: storage)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(s3={})))
    )
    delivery = {
        "deliveryId": "d" * 32,
        "files": [
            {
                "path": "/v1/files/f/download",
                "media": "image/png",
                "bucket": "b",
                "key": "k",
                "size": 9,
                "sha256": "0" * 64,
            }
        ],
    }
    client = Client()
    assert [frame async for frame in _stream_ui_artifacts(request, client, delivery)]
    assert client.messages[-1][1] == {"event": "done", "failed": ["/v1/files/f/download"]}


@pytest.mark.asyncio
async def test_unavailable_object_is_reported_without_exposing_storage_error(monkeypatch):
    from botocore.exceptions import ClientError

    from testing_agent.core import object_storage

    def missing(**kwargs):
        raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "private-key"}}, "GetObject")

    storage = SimpleNamespace(client=SimpleNamespace(get_object=missing))
    monkeypatch.setattr(object_storage, "ObjectStorage", lambda settings: storage)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(s3={})))
    )
    delivery = {
        "deliveryId": "f" * 32,
        "files": [
            {"path": "/v1/files/f/download", "media": "image/png", "bucket": "b", "key": "k"}
        ],
    }
    client = Client()
    assert [frame async for frame in _stream_ui_artifacts(request, client, delivery)] == []
    assert client.messages[-1][1] == {"event": "done", "failed": ["/v1/files/f/download"]}


@pytest.mark.asyncio
async def test_revoked_access_never_streams_artifact_and_notifies_sender():
    async def deny():
        raise PermissionError("revoked")

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(s3={})))
    )
    delivery = {"deliveryId": "c" * 32, "files": []}
    client = Client()
    with pytest.raises(PermissionError):
        await anext(_stream_ui_artifacts(request, client, delivery, deny))
    assert client.messages[-1][1] == {"event": "gone"}
