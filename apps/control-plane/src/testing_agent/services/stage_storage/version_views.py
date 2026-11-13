"""immutable version view using direct attempts for source details."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrNotFound
from testing_agent.domain.generation_chain import (
    artifact_summary,
    stage_label,
    stage_names,
    upstream_stages,
)
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.schemas.generation_chain import (
    ChainSourceInputsView,
    ChainStageVersionSummary,
    GenerationChainVersionDetail,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.stage_storage.views import attempt_source, version_batch
from testing_agent.services.ui_generation_sources import ui_source_inputs


async def version_detail(
    session: AsyncSession, task: AiGenerateTask, kind: DesignKind, version_id: str
) -> GenerationChainVersionDetail:
    """Caller must check project access and task ownership first."""
    row = await session.scalar(
        select(AiGenerateStageVersion).where(
            AiGenerateStageVersion.task_id == task.task_id,
            AiGenerateStageVersion.version_id == version_id,
        )
    )
    if row is None or row.stage not in stage_names(kind):
        raise ErrNotFound()
    display_stage = row.stage
    recorded = row.upstream_versions_json or {}
    recorded = {
        key: value
        for key, value in recorded.items()
        if key in upstream_stages(kind, display_stage) and isinstance(value, str) and value
    }
    summaries = []
    for parent_stage, parent_id in recorded.items():
        parent_task_id = task.task_id
        if kind == "function" and parent_stage == "extracting_text":
            parent_task = await session.scalar(
                select(AiGenerateTask)
                .where(
                    AiGenerateTask.requirement_id == task.requirement_id,
                    AiGenerateTask.task_type == "requirement_analysis",
                )
                .order_by(AiGenerateTask.created_at.desc(), AiGenerateTask.id.desc())
                .limit(1)
            )
            parent_task_id = parent_task.task_id if parent_task else ""
        parent = await session.scalar(
            select(AiGenerateStageVersion).where(
                AiGenerateStageVersion.task_id == parent_task_id,
                AiGenerateStageVersion.version_id == parent_id,
                AiGenerateStageVersion.stage == parent_stage,
            )
        )
        if parent is not None:
            summaries.append(
                ChainStageVersionSummary(
                    version_id=parent.version_id,
                    stage=parent.stage,
                    stage_label=stage_label(kind, parent.stage),
                    version_no=parent.version_no,
                    label=f"v{parent.version_no}",
                    summary=artifact_summary(
                        parent.stage, parent.artifact_content, parent.artifact_format
                    ),
                    artifact_format=parent.artifact_format,
                    created_at=parent.reviewed_at or parent.created_at,
                    reviewer_user_id=parent.reviewer_user_id,
                    source_run_id=parent.attempt_id,
                    source_batch_id=version_batch(parent) if kind == "ui" else "",
                    imported=False,
                )
            )
    source_inputs = None
    if kind == "ui":
        context = row.artifact_context_json or {}
        if "uiSourceInputs" in context:
            source_inputs = context["uiSourceInputs"]
        else:
            attempt = await session.scalar(
                select(AiGenerationAttempt).where(AiGenerationAttempt.id == row.attempt_id)
            )
            source_inputs = ui_source_inputs(attempt_source(attempt)) if attempt else None
    return GenerationChainVersionDetail(
        version_id=row.version_id,
        kind=kind,
        stage=display_stage,
        stage_label=stage_label(kind, display_stage),
        version_no=row.version_no,
        label=f"v{row.version_no}",
        summary=artifact_summary(display_stage, row.artifact_content, row.artifact_format),
        artifact_format=row.artifact_format,
        content=row.artifact_content,
        reviewer_user_id=row.reviewer_user_id,
        reviewed_at=row.reviewed_at,
        review_comment=row.review_comment,
        upstream_versions=recorded,
        upstream=summaries,
        source_inputs=ChainSourceInputsView.model_validate(source_inputs)
        if source_inputs
        else None,
    )
