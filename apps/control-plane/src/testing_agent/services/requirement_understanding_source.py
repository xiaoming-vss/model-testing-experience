"""Resolve approved requirement-understanding versions for downstream consumers.

Requirement understanding is stored as immutable generation-chain stage versions.
Downstream consumers read an explicitly selected or the latest approved version;
the requirement row keeps only the source material and is not a version store.
"""

from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.requirement_artifacts import requirement_content
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.repositories.generation_chain import GenerationChainRepository

UNDERSTANDING_STAGE = "feature_understanding"
SELECTION_ERROR = "选择的需求理解版本不存在或不属于当前需求"


async def approved_understanding(
    repository: GenerationChainRepository, requirement_id: str, version_id: str = ""
) -> AiGenerateStageVersion | None:
    """Return the selected or latest approved version; None when none was approved.

    An explicitly selected version that does not belong to this requirement's
    analysis chain is rejected instead of silently falling back to the latest.
    """
    task = await repository.task(requirement_id, "requirement_analysis")
    version = None
    if task is not None:
        version = (
            await repository.version(task.task_id, version_id)
            if version_id
            else await repository.latest_version(task.task_id, UNDERSTANDING_STAGE)
        )
    if version is None or version.stage != UNDERSTANDING_STAGE:
        if version_id:
            raise dynamic_error(ErrBadRequest, SELECTION_ERROR)
        return None
    return version


def understanding_source(version: AiGenerateStageVersion) -> str:
    """Validate the approved artifact and return the text consumed by prompts."""
    try:
        return requirement_content(version.artifact_content)
    except ValueError as exc:
        raise dynamic_error(ErrBadRequest, "需求理解版本内容无效，请重新生成并审核") from exc


def understanding_version_ref(version: AiGenerateStageVersion) -> dict[str, Any]:
    """Freeze the consumed version identity alongside the run snapshot."""
    return {
        "versionId": version.version_id,
        "versionNo": version.version_no,
        "taskId": version.task_id,
        "runId": version.attempt_id,
    }
