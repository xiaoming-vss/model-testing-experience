"""Resolve approved material versions for downstream generation tasks."""

from __future__ import annotations

import json
from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.requirement_artifacts import validate_artifact
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.repositories.generation_chain import GenerationChainRepository

MATERIAL_STAGE = "extracting_text"


async def approved_material(
    repository: GenerationChainRepository, requirement_id: str, version_id: str = ""
) -> AiGenerateStageVersion | None:
    """Select an immutable approved material version belonging to this requirement."""
    task = await repository.task(requirement_id, "requirement_analysis")
    version = None
    if task is not None:
        version = (
            await repository.version(task.task_id, version_id)
            if version_id
            else await repository.latest_version(task.task_id, MATERIAL_STAGE)
        )
    if version is None or version.stage != MATERIAL_STAGE:
        if version_id:
            raise dynamic_error(ErrBadRequest, "选择的材料整理版本不存在或不属于当前需求")
        return None
    return version


def material_source(version: AiGenerateStageVersion) -> str:
    """Return the complete validated material artifact for downstream prompts."""
    try:
        value = validate_artifact(version.artifact_content, "document_extraction")
    except ValueError as exc:
        raise dynamic_error(ErrBadRequest, "材料整理版本内容无效，请重新生成并审核") from exc
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def material_version_ref(version: AiGenerateStageVersion) -> dict[str, Any]:
    """Freeze the selected material version identity with the downstream input."""
    return {
        "versionId": version.version_id,
        "versionNo": version.version_no,
        "taskId": version.task_id,
        "runId": version.attempt_id,
    }
