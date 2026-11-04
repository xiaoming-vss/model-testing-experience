import asyncio
from types import SimpleNamespace

import pytest

from test_worker.ui import browser_cancellation


def test_cleanup_timeout_allows_browser_close_and_consumes_late_driver_error(
    monkeypatch,
):
    async def run():
        release = asyncio.Event()
        cleanup_started = asyncio.Event()
        loop = asyncio.get_running_loop()
        unhandled = []
        loop.set_exception_handler(lambda _loop, context: unhandled.append(context))

        async def stuck_context():
            cleanup_started.set()
            await release.wait()
            raise RuntimeError("secret browser URL")

        result = await browser_cancellation.close_browser_resource(
            stuck_context(), "task", "context"
        )
        assert cleanup_started.is_set()
        assert result is False
        # A caller can proceed to close the browser, which releases the driver.
        release.set()
        await asyncio.sleep(0.01)
        assert unhandled == []

    monkeypatch.setattr(browser_cancellation, "CLEANUP_TIMEOUT_SECONDS", 0.01)
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["case", "suite"])
@pytest.mark.parametrize("stop", [False, True])
def test_browser_start_timeout_or_stop_exits_driver(monkeypatch, tmp_path, kind, stop):
    from test_worker.contracts.types import (
        UiCaseRunSnapshot,
        UiCaseSnapshot,
        UiTestSuiteRunSnapshot,
    )
    from test_worker.ui import case_runner, suite_runner

    async def run():
        entered = asyncio.Event()
        driver_exit = asyncio.Event()
        settled = asyncio.Event()
        unhandled = []
        asyncio.get_running_loop().set_exception_handler(
            lambda _loop, context: unhandled.append(context)
        )

        async def stalled_launch(**_kwargs):
            entered.set()
            await driver_exit.wait()
            settled.set()
            raise RuntimeError("sensitive driver error")

        class Driver:
            chromium = SimpleNamespace(launch=stalled_launch)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                driver_exit.set()
                await asyncio.sleep(0)

        config = SimpleNamespace(artifacts_root_dir=str(tmp_path), trace_enabled=False)
        if kind == "case":
            monkeypatch.setattr(case_runner, "async_playwright", Driver)
            runner = case_runner.UiCaseRunner(config)
            snapshot = UiCaseRunSnapshot(
                task_id="task",
                run_id="run",
                case=UiCaseSnapshot(case_id="case", name="case"),
            )
        else:
            monkeypatch.setattr(suite_runner, "async_playwright", Driver)
            runner = suite_runner.UiSuiteRunner(config)
            snapshot = UiTestSuiteRunSnapshot(task_id="task", run_id="run", items=[])

        task = asyncio.create_task(runner.run(snapshot))
        await asyncio.wait_for(entered.wait(), 1)
        if stop:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(TimeoutError, match="浏览器启动超时"):
                await task
        await asyncio.wait_for(settled.wait(), 1)
        await asyncio.sleep(0)
        assert driver_exit.is_set()
        assert unhandled == []

    monkeypatch.setattr(browser_cancellation, "BROWSER_START_TIMEOUT_SECONDS", 0.01)
    asyncio.run(run())


def test_cleanup_reports_completion_and_does_not_log_exception_text(monkeypatch):
    messages = []
    monkeypatch.setattr(
        browser_cancellation.logger,
        "warn",
        lambda message, fields: messages.append((message, fields)),
    )

    async def run():
        async def success():
            return None

        async def failure():
            raise RuntimeError("secret browser URL")

        assert await browser_cancellation.close_browser_resource(
            success(), "task", "trace"
        )
        assert not await browser_cancellation.close_browser_resource(
            failure(), "task", "trace"
        )

    asyncio.run(run())
    assert messages[0][1]["errorType"] == "RuntimeError"
    assert "secret browser URL" not in str(messages)


@pytest.mark.parametrize("kind", ["case", "suite"])
def test_stopping_runner_closes_browser_after_context_and_trace_stall(
    monkeypatch, tmp_path, kind
):
    from test_worker.contracts.types import (
        UiCaseRunSnapshot,
        UiCaseSnapshot,
        UiTestSuiteRunSnapshot,
    )
    from test_worker.ui import case_runner, suite_runner

    async def run():
        page_start = asyncio.Event()
        browser_closed = asyncio.Event()
        completed = []

        class Trace:
            async def start(self, **_kwargs):
                pass

            async def stop(self, **_kwargs):
                await browser_closed.wait()
                completed.append("trace")

        class Context:
            tracing = Trace()

            async def new_page(self):
                page_start.set()
                await asyncio.Event().wait()

            async def close(self):
                await browser_closed.wait()
                completed.append("context")

        class Browser:
            async def new_context(self, **_kwargs):
                return Context()

            async def close(self):
                browser_closed.set()
                await asyncio.sleep(0)

        async def launch(**_kwargs):
            return Browser()

        class Driver:
            chromium = SimpleNamespace(launch=launch)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                await asyncio.sleep(0)

        config = SimpleNamespace(artifacts_root_dir=str(tmp_path), trace_enabled=True)
        if kind == "case":
            monkeypatch.setattr(case_runner, "async_playwright", Driver)
            runner = case_runner.UiCaseRunner(config)
            snapshot = UiCaseRunSnapshot(
                task_id="task",
                run_id="run",
                case=UiCaseSnapshot(case_id="case", name="case"),
            )
        else:
            monkeypatch.setattr(suite_runner, "async_playwright", Driver)
            runner = suite_runner.UiSuiteRunner(config)
            snapshot = UiTestSuiteRunSnapshot(task_id="task", run_id="run", items=[])

        task = asyncio.create_task(runner.run(snapshot))
        await asyncio.wait_for(page_start.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        await asyncio.sleep(0)
        assert browser_closed.is_set()
        assert sorted(completed) == ["context", "trace"]

    monkeypatch.setattr(browser_cancellation, "CLEANUP_TIMEOUT_SECONDS", 0.01)
    asyncio.run(run())
