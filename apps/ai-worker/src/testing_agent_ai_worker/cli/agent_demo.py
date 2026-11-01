from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable

from testing_agent_ai_worker.agent.demo import run_demo


async def run_cli_demo(
    *,
    message: str = "What time is it in Tokyo?",
    session_key: str = "demo:agent",
    config_path: str | None = None,
    workspace: str | None = None,
    backend: str | None = None,
    runner: Callable[..., Awaitable[str]] = run_demo,
    printer: Callable[[str], None] = print,
) -> int:
    kwargs = {
        "message": message,
        "session_key": session_key,
        "config_path": config_path,
        "workspace": workspace,
    }
    if backend is not None:
        kwargs["backend"] = backend
    content = await runner(**kwargs)
    printer(content)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one prompt with the configured backend.")
    parser.add_argument("--config-path", default=None)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--backend", choices=("nanobot", "pi"), default=None)
    parser.add_argument("--message", default="What time is it in Tokyo?")
    parser.add_argument("--session-key", default="demo:agent")
    values = {key: value for key, value in vars(parser.parse_args()).items() if value is not None}
    return asyncio.run(run_cli_demo(**values))


if __name__ == "__main__":
    sys.exit(main())
