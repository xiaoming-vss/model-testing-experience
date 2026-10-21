"""Run one requirement-analysis skill in an isolated pi session."""

from collections.abc import Callable
from typing import Any

from testing_agent_ai_worker_pi.pi_runtime.prompt import build_skill_message


def _default_from_config(**kwargs: Any) -> Any:
    from testing_agent_ai_worker_pi.pi_runtime.client import Pi

    return Pi.from_config(**kwargs)


async def run_skill_step(
    *,
    input_text: str,
    session_key: str,
    skill_name: str,
    config_path: str | None = None,
    workspace: str | None = None,
    extra_instruction: str = "",
    media: list[str] | None = None,
    from_config: Callable[..., Any] | None = None,
) -> Any:
    """执行需求分析单步 skill。"""

    factory = from_config or _default_from_config

    async with factory(config_path=config_path, workspace=workspace) as bot:
        result = await bot.run(
            build_skill_message(
                skill_name=skill_name,
                body_text=input_text,
                extra_instruction=extra_instruction,
            ),
            session_key=session_key,
            **({"media": media} if media else {}),
        )
    # Preserve SDK failure/truncation metadata for output validation.
    return result
