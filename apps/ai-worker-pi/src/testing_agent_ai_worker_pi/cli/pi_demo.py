from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable

from testing_agent_ai_worker_pi.pi.runner import run_demo


async def run_cli_demo(
    *,
    message: str = "What time is it in Tokyo?",
    session_key: str = "demo:pi",
    config_path: str | None = None,
    workspace: str | None = None,
    runner: Callable[..., Awaitable[str]] = run_demo,
    printer: Callable[[str], None] = print,
) -> int:
    content = await runner(
        message=message,
        session_key=session_key,
        config_path=config_path,
        workspace=workspace,
    )
    printer(content)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Pi prompt with task credentials.")
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--message", default="What time is it in Tokyo?")
    parser.add_argument("--session-key", default="demo:pi")
    return asyncio.run(run_cli_demo(**vars(parser.parse_args())))


if __name__ == "__main__":
    sys.exit(main())
