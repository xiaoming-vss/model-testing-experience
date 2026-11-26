"""Minimal demo runner shared by every execution backend."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from testing_agent_ai_worker.agent import create_agent
from testing_agent_ai_worker.agent.base import AgentConfigPath


async def run_demo(
    *,
    message: str,
    session_key: str,
    config_path: str | None = None,
    workspace: str | None = None,
    backend: str | None = None,
    from_config: Callable[..., Any] | None = None,
) -> str:
    """运行最小 agent demo。"""

    if backend and config_path:
        config_path = AgentConfigPath(config_path, backend)
    factory = from_config or create_agent
    async with factory(config_path=config_path, workspace=workspace) as bot:
        result = await bot.run(message, session_key=session_key)
    return result.content
