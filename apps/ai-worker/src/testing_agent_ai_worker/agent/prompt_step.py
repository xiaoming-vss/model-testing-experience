"""Run one agent call without a platform skill or skill message."""

from __future__ import annotations

from testing_agent_ai_worker.agent import create_agent
from testing_agent_ai_worker.agent.base import AgentResult


async def run_agent_prompt(
    *,
    input_text: str,
    session_key: str,
    config_path: str | None = None,
    workspace: str | None = None,
    tools: tuple[str, ...] | None = None,
) -> AgentResult:
    """Send an already assembled prompt to the configured agent backend.

    Unlike ``run_skill_step`` this does not inject a skill instruction; the
    caller owns the prompt and the tool allowlist. Only the Pi backend supports
    a per-call tool selection.
    """

    async with create_agent(config_path=config_path, workspace=workspace, tools=tools) as bot:
        return await bot.run(input_text, session_key=session_key)
