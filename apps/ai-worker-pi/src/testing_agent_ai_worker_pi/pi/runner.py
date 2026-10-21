"""Run a standalone Pi invocation for the command-line demo."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _default_from_config(**kwargs: Any) -> Any:
    """Construct the task-scoped RPC client."""

    from testing_agent_ai_worker_pi.pi_runtime.client import Pi

    return Pi.from_config(**kwargs)


async def run_demo(
    *,
    message: str,
    session_key: str,
    config_path: str | None = None,
    workspace: str | None = None,
    from_config: Callable[..., Any] | None = None,
) -> str:
    """运行最小 pi demo。"""

    factory = from_config or _default_from_config
    async with factory(config_path=config_path, workspace=workspace) as bot:
        result = await bot.run(message, session_key=session_key)
    return result.content
