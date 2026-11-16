from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from testing_agent_ai_worker.agent.base import AgentConfigPath
from testing_agent_ai_worker.skill_names import API_EXTRACT_SKILL, API_GENERATE_SKILL
from testing_agent_ai_worker.tasks.api_case_generate.chain import ChainRunResult, run_chain

DEFAULT_EXTRACTOR_SKILL_NAME = API_EXTRACT_SKILL
DEFAULT_GENERATOR_SKILL_NAME = API_GENERATE_SKILL


async def run_chain_demo(
    *,
    source_json_path: str,
    session_key: str = "demo:agent-chain",
    extractor_skill_name: str = DEFAULT_EXTRACTOR_SKILL_NAME,
    generator_skill_name: str = DEFAULT_GENERATOR_SKILL_NAME,
    config_path: str | None = None,
    workspace: str | None = None,
    backend: str | None = None,
    extra_instruction: str = "",
    runner: Callable[..., Awaitable[ChainRunResult]] = run_chain,
    printer: Callable[[str], None] = print,
) -> int:
    source_text = Path(source_json_path).read_text(encoding="utf-8")
    if backend and config_path:
        config_path = AgentConfigPath(config_path, backend)
    result = await runner(
        source_text=source_text,
        session_key=session_key,
        extractor_skill_name=extractor_skill_name,
        generator_skill_name=generator_skill_name,
        config_path=config_path,
        workspace=workspace,
        extra_instruction=extra_instruction,
    )
    printer("=== extractor output ===")
    printer(result.extractor_output)
    printer("=== yaml generator output ===")
    printer(result.generator_output)
    return 0


def main(
    *,
    source_json_path: str | None = None,
    session_key: str = "demo:agent-chain",
    extractor_skill_name: str = DEFAULT_EXTRACTOR_SKILL_NAME,
    generator_skill_name: str = DEFAULT_GENERATOR_SKILL_NAME,
    config_path: str | None = None,
    workspace: str | None = None,
    backend: str | None = None,
    extra_instruction: str = "",
) -> int:
    if source_json_path is None:
        parser = argparse.ArgumentParser(
            description="Generate API cases from an interface JSON or legacy OpenAPI JSON file."
        )
        parser.add_argument("--source-json-path", required=True)
        parser.add_argument("--session-key", default=session_key)
        parser.add_argument("--extractor-skill-name", default=extractor_skill_name)
        parser.add_argument("--generator-skill-name", default=generator_skill_name)
        parser.add_argument("--config-path", default=config_path)
        parser.add_argument("--workspace", default=workspace)
        parser.add_argument("--backend", choices=("nanobot", "pi"), default=backend)
        parser.add_argument("--extra-instruction", default=extra_instruction)
        args = parser.parse_args()
        return main(**vars(args))
    return asyncio.run(
        run_chain_demo(
            source_json_path=source_json_path,
            session_key=session_key,
            extractor_skill_name=extractor_skill_name,
            generator_skill_name=generator_skill_name,
            config_path=config_path,
            workspace=workspace,
            backend=backend,
            extra_instruction=extra_instruction,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
