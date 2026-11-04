from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError

from testing_agent.services import test_run_notifications as notifications


@pytest.mark.asyncio
async def test_publish_reuses_connection_pool_and_closes_it_on_shutdown(monkeypatch):
    events = []
    clients = []

    class RedisClient:
        def pipeline(self, transaction):
            assert transaction
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def lpush(self, queue, message):
            events.append(("push", queue, message))

        def ltrim(self, queue, first, last):
            events.append(("trim", queue, first, last))

        def expire(self, queue, seconds):
            events.append(("expire", queue, seconds))

        def publish(self, channel, message):
            events.append((channel, message))

        async def execute(self):
            events.append("executed")

        async def aclose(self):
            events.append("closed")

    monkeypatch.setattr(
        notifications, "get_settings", lambda: SimpleNamespace(test_run_redis_url="redis://example")
    )

    def create(*args, **kwargs):
        client = RedisClient()
        clients.append(client)
        return client

    monkeypatch.setattr(notifications.Redis, "from_url", create)
    await notifications.notify_task_available()
    await notifications.notify_task_available()
    assert len(clients) == 1
    await notifications.close_notification_clients()
    one_notification = [
        ("push", notifications.TASK_WAKE_QUEUE, "available"),
        ("trim", notifications.TASK_WAKE_QUEUE, 0, 9999),
        ("expire", notifications.TASK_WAKE_QUEUE, 60),
        (notifications.TASK_CHANNEL, "available-v2"),
        "executed",
    ]
    assert events == one_notification * 2 + ["closed"]


@pytest.mark.asyncio
async def test_notification_failure_does_not_fail_a_committed_submission(monkeypatch, caplog):
    class RedisClient:
        def pipeline(self, transaction):
            raise ConnectionError("credential should not appear in logs")

        async def aclose(self):
            pass

    monkeypatch.setattr(
        notifications, "get_settings", lambda: SimpleNamespace(test_run_redis_url="redis://example")
    )
    monkeypatch.setattr(notifications.Redis, "from_url", lambda *a, **kw: RedisClient())
    await notifications.notify_task_available()
    assert "credential" not in caplog.text
    await notifications.close_notification_clients()


@pytest.mark.asyncio
async def test_ui_step_progress_checks_lease_redacts_and_notifies_after_commit(monkeypatch):
    from testing_agent.schemas.workers import WorkerTaskEventRequest
    from testing_agent.services import worker_task as module

    task = SimpleNamespace(
        task_id="task",
        task_type="case_debug",
        run_id="run",
        worker_id="w",
        status="running",
        lease_expires_at=None,
    )
    run = SimpleNamespace(step_results_json=[])
    actions = []

    class Repository:
        session = object()

        async def get_ui_case_run(self, run_id):
            assert run_id == "run"
            return run

        async def commit(self):
            actions.append("commit")

    async def find_task(*args):
        return task

    async def authorize(*args, **kwargs):
        return SimpleNamespace(run=object())

    async def notify(domain, run_id):
        actions.append((domain, run_id))

    monkeypatch.setattr(module, "find_task", find_task)
    monkeypatch.setattr(module, "authorize_execution", authorize)
    monkeypatch.setattr(module, "private_payload", lambda run: {"secrets": ["hidden-value"]})
    monkeypatch.setattr(module, "notify_run_changed", notify)
    service = module.WorkerTaskService(Repository())
    body = WorkerTaskEventRequest(
        workerId="w", stepResults=[{"status": "running", "actualValue": "hidden-value"}]
    )
    await service.update_ui_steps("task", None, body)
    assert run.step_results_json == [{"status": "running", "actualValue": "********"}]
    assert actions == ["commit", ("ui", "run")]


@pytest.mark.asyncio
async def test_stream_restricts_debug_run_to_its_initiator():
    from testing_agent.core.errors import ErrForbidden
    from testing_agent.routers.test_run_events import test_run_events as open_events

    class ApiCases:
        repository = SimpleNamespace(get_run=_async_value(SimpleNamespace(trigger_user_id="owner")))

        async def get_run(self, user, run_id):
            return {}

    with pytest.raises(type(ErrForbidden)):
        await open_events(
            "api-case", "run", SimpleNamespace(), "other", None, ApiCases(), None, None
        )


def _async_value(value):
    async def get(*args):
        return value

    return get


@pytest.mark.asyncio
async def test_stream_subscribes_before_ready_and_forwards_notifications(monkeypatch):
    from testing_agent.routers import test_run_events as module

    calls = []

    class PubSub:
        async def subscribe(self, channel):
            calls.append(("subscribe", channel))

        async def get_message(self, **kwargs):
            if kwargs.get("ignore_subscribe_messages") is False:
                return {"type": "subscribe"}
            return {"data": b"changed"}

        async def aclose(self):
            calls.append("pubsub closed")

    class Client:
        def pubsub(self):
            return PubSub()

        async def aclose(self):
            calls.append("client closed")

    class Session:
        async def rollback(self):
            calls.append("released")

    class Collections:
        async def get(self, user, run):
            calls.append(("authorized", user, run))

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=SimpleNamespace(test_run_redis_url="redis://example"))
        ),
        is_disconnected=_async_value(False),
    )
    monkeypatch.setattr(module.Redis, "from_url", lambda *args, **kwargs: Client())
    response = await module.test_run_events(
        "api-collection", "run", request, "user", Session(), None, Collections(), None
    )
    stream = response.body_iterator
    assert await anext(stream) == "event: ready\ndata: {}\n\n"
    assert await anext(stream) == "event: changed\ndata: {}\n\n"
    await stream.aclose()
    assert calls == [
        ("authorized", "user", "run"),
        "released",
        ("subscribe", "mtx:api-ui:run:api:run"),
        "pubsub closed",
        "client closed",
    ]


@pytest.mark.asyncio
async def test_debug_stream_subscribes_before_submitting_fast_run(monkeypatch):
    import json

    from testing_agent.routers import test_debug_stream as module
    from testing_agent.services.integration_credentials import IntegrationCredentialCipher

    calls = []
    encrypted = IntegrationCredentialCipher("safe-test-key").encrypt(
        json.dumps({"domain": "api", "runId": "run", "result": {"status": "success"}})
    )

    class PubSub:
        async def subscribe(self, channel):
            calls.append(("subscribe", channel))

        async def get_message(self, **kwargs):
            if kwargs.get("ignore_subscribe_messages") is False:
                return {"type": "subscribe"}
            return {"data": json.dumps({"event": "finished", "ciphertext": encrypted}).encode()}

        async def aclose(self):
            calls.append("pubsub closed")

    class Client:
        def pubsub(self):
            return PubSub()

        async def aclose(self):
            calls.append("client closed")

    class Session:
        async def rollback(self):
            calls.append("released")

    async def submit():
        calls.append("submit")
        return {"runId": "run", "status": "pending"}

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(
                    test_run_redis_url="redis://example", integration_key="safe-test-key"
                )
            )
        ),
        is_disconnected=_async_value(False),
    )
    monkeypatch.setattr(module.Redis, "from_url", lambda *args, **kwargs: Client())
    response = await module._start_stream(request, "api", "run", submit, Session())
    stream = response.body_iterator
    assert '"runId": "run"' in await anext(stream)
    assert '"status": "success"' in await anext(stream)
    await stream.aclose()
    assert calls[:3] == [("subscribe", "mtx:api-ui:run:api:run"), "submit", "released"]


@pytest.mark.asyncio
async def test_final_result_is_encrypted_and_bound_to_its_run(monkeypatch):
    import json

    from testing_agent.services.integration_credentials import IntegrationCredentialCipher

    messages = []

    async def publish(channel, message, **kwargs):
        messages.append((channel, message))

    monkeypatch.setattr(notifications, "_publish", publish)
    monkeypatch.setattr(
        notifications, "get_settings", lambda: SimpleNamespace(integration_key="safe-test-key")
    )
    await notifications.notify_run_finished("api", "run", {"response": "private-response"})
    assert "private-response" not in messages[0][1]
    payload = json.loads(messages[0][1])
    decrypted = json.loads(
        IntegrationCredentialCipher("safe-test-key").decrypt(payload["ciphertext"])
    )
    assert decrypted == {
        "domain": "api",
        "runId": "run",
        "result": {"response": "private-response"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "states,expected", [([], "offline"), ([b"busy"], "busy"), ([b"busy", b"idle"], "available")]
)
async def test_availability_reports_advisory_worker_presence(monkeypatch, states, expected):
    from testing_agent.routers import test_run_availability as module

    class RedisClient:
        async def scan_iter(self, **kwargs):
            for index in range(len(states)):
                yield str(index).encode()

        async def mget(self, keys):
            return states

        async def aclose(self):
            pass

    monkeypatch.setattr(module.Redis, "from_url", lambda *args, **kwargs: RedisClient())
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=SimpleNamespace(test_run_redis_url="redis://example"))
        )
    )
    response = await module.availability(request, "user")
    assert response["data"]["state"] == expected


def test_database_pool_configuration_is_bounded():
    from testing_agent.core.config import Settings

    default = Settings.from_mapping({})
    assert (default.db_pool_size, default.db_max_overflow) == (20, 10)
    configured = Settings.from_mapping(
        {"data": {"db": {"user": {"pool_size": 12, "max_overflow": 3}}}}
    )
    assert (configured.db_pool_size, configured.db_max_overflow) == (12, 3)
    for invalid in (0, -1, 101, True, "20"):
        with pytest.raises(ValueError):
            Settings.from_mapping({"data": {"db": {"user": {"pool_size": invalid}}}})
    for invalid in (-1, 101, True, "10"):
        with pytest.raises(ValueError):
            Settings.from_mapping({"data": {"db": {"user": {"max_overflow": invalid}}}})


@pytest.mark.asyncio
async def test_debug_stream_rechecks_access_before_delivering_sensitive_result(monkeypatch):
    import json

    from testing_agent.core.errors import ErrForbidden
    from testing_agent.routers import test_debug_stream as module
    from testing_agent.services.integration_credentials import IntegrationCredentialCipher

    ciphertext = IntegrationCredentialCipher("safe-test-key").encrypt(
        json.dumps({"domain": "api", "runId": "run", "result": {"response": "private"}})
    )

    class PubSub:
        async def subscribe(self, channel):
            pass

        async def get_message(self, **kwargs):
            if kwargs.get("ignore_subscribe_messages") is False:
                return {"type": "subscribe"}
            return {"data": json.dumps({"event": "finished", "ciphertext": ciphertext}).encode()}

        async def aclose(self):
            pass

    class Client:
        def pubsub(self):
            return PubSub()

        async def aclose(self):
            pass

    async def denied():
        raise ErrForbidden()

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(
                    test_run_redis_url="redis://example", integration_key="safe-test-key"
                )
            )
        ),
        is_disconnected=_async_value(False),
    )
    session = SimpleNamespace(rollback=_async_value(None))
    monkeypatch.setattr(module.Redis, "from_url", lambda *args, **kwargs: Client())
    response = await module._start_stream(request, "api", "run", _async_value({}), session, denied)
    stream = response.body_iterator
    assert "event: started" in await anext(stream)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
