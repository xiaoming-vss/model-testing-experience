"""One agent call retaining error and completion metadata for caller validation."""

from __future__ import annotations

from testing_agent_ai_worker.agent import create_agent
from testing_agent_ai_worker.agent.base import AgentResult
from testing_agent_ai_worker.agent.prompt import build_skill_message


async def run_skill_step(
    *,
    input_text: str,
    session_key: str,
    skill_name: str,
    config_path: str | None = None,
    workspace: str | None = None,
    extra_instruction: str = "",
    media: list[str] | None = None,
) -> AgentResult:
    async with create_agent(config_path=config_path, workspace=workspace) as bot:
        return await bot.run(
            build_skill_message(
                skill_name=skill_name, body_text=input_text, extra_instruction=extra_instruction
            ),
            session_key=session_key,
            **({"media": media} if media else {}),
        )
