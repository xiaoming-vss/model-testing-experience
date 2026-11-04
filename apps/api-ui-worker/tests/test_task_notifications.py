import asyncio
from types import SimpleNamespace

from test_worker.poller.task_poller import TaskPoller


def test_idle_and_error_retry_windows_are_bounded(monkeypatch):
    from test_worker.poller import task_poller

    monkeypatch.setattr(task_poller.random, "uniform", lambda low, _high: low)
    assert task_poller._fallback_wait_seconds(30000) == 27
    monkeypatch.setattr(task_poller.random, "uniform", lambda _low, high: high)
    assert task_poller._fallback_wait_seconds(30000) == 33


def test_notification_during_queue_check_wakes_worker_without_waiting_for_timeout():
    async def run():
        wake = asyncio.Event()
        calls = []

        class Client:
            def claim_task(self):
                calls.append("ui")
                if len(calls) == 1:
                    wake.set()
                return None

            def claim_api_task(self):
                calls.append("api")
                if len(calls) >= 4:
                    raise asyncio.CancelledError()
                return None

        poller = TaskPoller(
            SimpleNamespace(poll_interval_ms=30000), Client(), None, None
        )
        try:
            await asyncio.wait_for(poller._poll(wake), timeout=1)
        except asyncio.CancelledError:
            pass
        assert calls == ["ui", "api", "ui", "api"]

    asyncio.run(run())


def test_each_queue_hint_wakes_one_idle_worker(monkeypatch):
    from test_worker.poller import task_notifications

    async def run():
        tokens = asyncio.Queue()
        ready = [asyncio.Event(), asyncio.Event()]

        class Client:
            async def brpop(self, key, timeout):
                assert key == task_notifications.TASK_WAKE_QUEUE
                return await tokens.get()

            async def aclose(self):
                pass

        monkeypatch.setattr(
            task_notifications.Redis, "from_url", lambda *a, **kw: Client()
        )
        workers = [
            asyncio.create_task(
                task_notifications.wait_for_task("redis://test", event, 0.2)
            )
            for event in ready
        ]
        await asyncio.sleep(0)
        await tokens.put("available")
        done, pending = await asyncio.wait(
            workers, timeout=0.1, return_when=asyncio.FIRST_COMPLETED
        )
        assert len(done) == len(pending) == 1
        await tokens.put("available")
        await asyncio.gather(*workers)

    asyncio.run(run())


def test_new_worker_ignores_new_broadcast_but_accepts_old_server(monkeypatch):
    from test_worker.poller import task_notifications

    async def run():
        messages = asyncio.Queue()
        wake = asyncio.Event()

        class PubSub:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def subscribe(self, channel):
                assert channel == task_notifications.TASK_CHANNEL

            async def get_message(self, **kwargs):
                if kwargs.get("ignore_subscribe_messages") is False:
                    return {"type": "subscribe"}
                return await messages.get()

        class Client:
            def pubsub(self):
                return PubSub()

            async def aclose(self):
                pass

        monkeypatch.setattr(
            task_notifications.Redis, "from_url", lambda *a, **kw: Client()
        )
        listener = asyncio.create_task(
            task_notifications.listen_for_tasks("redis://test", wake)
        )
        await asyncio.wait_for(wake.wait(), 1)
        wake.clear()
        await messages.put({"data": b"available-v2"})
        await asyncio.sleep(0.01)
        assert not wake.is_set()
        await messages.put({"data": b"available"})
        await asyncio.wait_for(wake.wait(), 1)
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

    asyncio.run(run())


def test_worker_reconnects_and_wakes_after_notification_connection_fails(monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError
    from test_worker.poller import task_notifications

    async def run():
        wake = asyncio.Event()
        fail = asyncio.Event()
        clients = []

        class PubSub:
            def __init__(self, index):
                self.index = index
                self.acknowledged = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def subscribe(self, _channel):
                pass

            async def get_message(self, **_kwargs):
                if not self.acknowledged:
                    self.acknowledged = True
                    return {"type": "subscribe"}
                if self.index == 0:
                    await fail.wait()
                    raise RedisConnectionError("disconnected")
                await asyncio.Event().wait()

        class Client:
            def __init__(self, index):
                self.index = index

            def pubsub(self):
                return PubSub(self.index)

            async def aclose(self):
                pass

        def create(*_args, **_kwargs):
            client = Client(len(clients))
            clients.append(client)
            return client

        monkeypatch.setattr(task_notifications.Redis, "from_url", create)
        monkeypatch.setattr(task_notifications, "_reconnect_delay", lambda: 0.01)
        listener = asyncio.create_task(
            task_notifications.listen_for_tasks("redis://test", wake)
        )
        try:
            await asyncio.wait_for(wake.wait(), 1)
            wake.clear()
            fail.set()
            await asyncio.wait_for(wake.wait(), 1)
            assert len(clients) >= 2
        finally:
            listener.cancel()
            await asyncio.gather(listener, return_exceptions=True)

    asyncio.run(run())


def test_notification_reconnect_delay_stays_bounded(monkeypatch):
    from test_worker.poller import task_notifications

    monkeypatch.setattr(task_notifications.random, "uniform", lambda low, _high: low)
    assert task_notifications._reconnect_delay() == 2
    monkeypatch.setattr(task_notifications.random, "uniform", lambda _low, high: high)
    assert task_notifications._reconnect_delay() == 4


def test_step_progress_reports_running_and_completed_without_stopping_execution():
    from test_worker.contracts.types import UiStepDefinition, UiStepRunResult
    from test_worker.ui.step_progress import report_steps

    calls = []

    class Client:
        def report_ui_steps(self, task_id, item_id, steps):
            calls.append((task_id, item_id, steps))

    async def run():
        step = UiStepDefinition(keyword="click", step_name="submit")
        await report_steps(Client(), "task", "item", [], step, 1, "now")
        result = UiStepRunResult(
            1, "submit", "click", "success", True, "now", "later", 2
        )
        await report_steps(Client(), "task", "item", [result])

    asyncio.run(run())
    assert calls[0][2][0]["status"] == "running"
    assert calls[1][2][0]["status"] == "success"


def test_user_stop_cancels_inflight_execution_and_keeps_worker_alive():
    from test_worker.poller.task_poller import UserStopped

    async def run():
        entered = asyncio.Event()
        canceled = asyncio.Event()

        class Client:
            def task_stop_requested(self, domain, task_id):
                return True

        async def operation():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                canceled.set()

        poller = TaskPoller(SimpleNamespace(redis_url=""), Client(), None, None)
        try:
            await asyncio.wait_for(
                poller._run_until_stopped("ui", "task", operation()), 2
            )
            raise AssertionError("stop should interrupt the operation")
        except UserStopped:
            pass
        assert entered.is_set() and canceled.is_set()

    asyncio.run(run())


def test_worker_prefers_shared_fifo_endpoint_and_preserves_domain():
    calls = []

    class Client:
        def claim_next_task(self):
            calls.append("next")
            return {
                "domain": "api",
                "taskId": "old",
                "taskType": "api_case_debug",
                "runId": "r",
            }

        def claim_task(self):
            raise AssertionError("legacy UI endpoint must not be queried")

        def claim_api_task(self):
            raise AssertionError("legacy API endpoint must not be queried")

    class Poller(TaskPoller):
        async def _handle_api_task(self, task):
            assert task["taskId"] == "old"
            raise asyncio.CancelledError()

    async def run():
        poller = Poller(
            SimpleNamespace(
                worker_id="w", mode="poll", poll_interval_ms=1, redis_url=""
            ),
            Client(),
            None,
            None,
        )
        try:
            await poller.start()
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert calls == ["next"]


def test_worker_presence_tracks_busy_and_idle():
    from test_worker.poller import task_notifications

    async def run():
        calls = []
        published = asyncio.Event()
        busy, refresh = asyncio.Event(), asyncio.Event()

        class Client:
            async def set(self, key, value, ex):
                calls.append((key, value, ex))
                published.set()

            async def aclose(self):
                pass

        original = task_notifications.Redis.from_url
        task_notifications.Redis.from_url = lambda *args, **kwargs: Client()
        try:
            task = asyncio.create_task(
                task_notifications.publish_worker_presence(
                    "redis://test", "w", busy, refresh
                )
            )
            await asyncio.wait_for(published.wait(), 1)
            published.clear()
            busy.set()
            refresh.set()
            await asyncio.wait_for(published.wait(), 1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        finally:
            task_notifications.Redis.from_url = original
        assert calls == [
            ("mtx:api-ui:workers:w", "idle", 35),
            ("mtx:api-ui:workers:w", "busy", 35),
        ]

    asyncio.run(run())


def test_completion_cleanup_does_not_log_expected_missing_heartbeat(monkeypatch):
    from test_worker.control_plane.client import ControlPlaneRequestError
    from test_worker.poller import task_poller

    warnings = []

    class Client:
        def report_task_heartbeat(self, task_id, payload):
            raise ControlPlaneRequestError("already retired", 404)

    async def run():
        poller = TaskPoller(
            SimpleNamespace(worker_id="w", heartbeat_interval_ms=1),
            Client(),
            None,
            None,
        )
        poller._finishing_tasks.add("task")
        await asyncio.wait_for(poller._heartbeat_loop("task"), 1)

    monkeypatch.setattr(task_poller.logger, "warn", lambda *args: warnings.append(args))
    asyncio.run(run())
    assert warnings == []


def test_stopping_browser_step_drains_the_inflight_driver_reply():
    from test_worker.ui.browser_cancellation import await_browser_operation

    async def run():
        entered, closed = asyncio.Event(), asyncio.Event()
        events = []

        class Context:
            async def close(self):
                events.append("close")
                closed.set()

        class Page:
            context = Context()

        async def driver_operation():
            entered.set()
            await closed.wait()
            events.append("driver replied")
            raise RuntimeError("navigation interrupted")

        task = asyncio.create_task(await_browser_operation(driver_operation(), Page()))
        await entered.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert events == ["close", "driver replied"]

    asyncio.run(run())
