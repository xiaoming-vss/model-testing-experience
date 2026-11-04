import asyncio
from types import SimpleNamespace

import pytest

from test_worker.ui import playwright_session


def test_late_driver_handle_is_reaped_after_stop_was_not_confirmed(monkeypatch):
    async def run():
        entered = asyncio.Event()
        killed = asyncio.Event()

        class Process:
            returncode = None

            def kill(self):
                self.returncode = -9
                killed.set()

            async def wait(self):
                await killed.wait()
                return self.returncode

        process = Process()
        transport = SimpleNamespace(_proc=None)

        class Manager:
            _connection = SimpleNamespace(_transport=transport)

            async def __aenter__(self):
                entered.set()
                await asyncio.Event().wait()

        async def execution():
            async with playwright_session.playwright_session(Manager, "task"):
                raise AssertionError("driver did not start")

        task = asyncio.create_task(execution())
        await entered.wait()
        task.cancel()
        with pytest.raises(RuntimeError, match="无法确认浏览器驱动已退出"):
            await asyncio.wait_for(task, 1)
        transport._proc = process
        await asyncio.wait_for(killed.wait(), 1)
        await asyncio.sleep(0)
        assert process.returncode == -9

    monkeypatch.setattr(playwright_session, "DRIVER_HANDLE_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(playwright_session, "DRIVER_LATE_REAP_SECONDS", 1)
    asyncio.run(run())


@pytest.mark.parametrize("stop", [False, True])
def test_stalled_driver_start_is_reaped(monkeypatch, stop):
    async def run():
        started = asyncio.Event()
        killed = asyncio.Event()

        class Process:
            returncode = None

            def kill(self):
                self.returncode = -9
                killed.set()

            async def wait(self):
                await killed.wait()
                return self.returncode

        process = Process()

        class Manager:
            _connection = SimpleNamespace(_transport=SimpleNamespace(_proc=process))

            async def __aenter__(self):
                started.set()
                await killed.wait()
                raise RuntimeError("sensitive driver error")

        async def execution():
            async with playwright_session.playwright_session(Manager, "task"):
                raise AssertionError("driver did not start")

        task = asyncio.create_task(execution())
        await started.wait()
        if stop:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(TimeoutError, match="浏览器驱动启动超时"):
                await task
        assert process.returncode == -9

    monkeypatch.setattr(playwright_session, "DRIVER_START_TIMEOUT_SECONDS", 0.01)
    asyncio.run(run())


@pytest.mark.parametrize("cancel", [False, True])
def test_stalled_driver_is_killed_and_original_cancellation_survives(
    monkeypatch, cancel
):
    async def run():
        exit_requested = asyncio.Event()
        released = asyncio.Event()

        class Process:
            returncode = None

            def kill(self):
                self.returncode = -9
                released.set()

        process = Process()

        class Manager:
            _connection = SimpleNamespace(_transport=SimpleNamespace(_proc=process))

            async def __aenter__(self):
                return object()

            async def __aexit__(self, *_args):
                exit_requested.set()
                await released.wait()

        async def execution():
            async with playwright_session.playwright_session(Manager, "task"):
                if cancel:
                    raise asyncio.CancelledError()

        expected = asyncio.CancelledError if cancel else RuntimeError
        with pytest.raises(expected):
            await asyncio.wait_for(execution(), 1)
        assert exit_requested.is_set()
        assert process.returncode == -9

    monkeypatch.setattr(playwright_session, "DRIVER_STOP_TIMEOUT_SECONDS", 0.01)
    asyncio.run(run())


def test_missing_driver_handle_cannot_confirm_successful_stop(monkeypatch):
    async def run():
        release = asyncio.Event()

        class Manager:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *_args):
                await release.wait()

        try:
            with pytest.raises(RuntimeError, match="浏览器驱动未能退出"):
                async with playwright_session.playwright_session(Manager, "task"):
                    raise asyncio.CancelledError()
        finally:
            release.set()
            await asyncio.sleep(0)

    monkeypatch.setattr(playwright_session, "DRIVER_STOP_TIMEOUT_SECONDS", 0.01)
    asyncio.run(run())
