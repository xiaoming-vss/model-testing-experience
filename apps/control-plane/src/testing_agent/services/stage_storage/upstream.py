"""upstream version selection without old run ledger reads."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_chain import stage_label, upstream_stages
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.stage_storage.views import version_batch


async def select_upstream_versions(
    session: AsyncSession,
    task: AiGenerateTask,
    kind: DesignKind,
    stage: str,
    selected_ids: dict[str, str],
) -> dict[str, AiGenerateStageVersion]:
    """Resolve and lock immutable upstreams inside the caller's transaction."""
    expected = set(upstream_stages(kind, stage))
    if set(selected_ids) - expected:
        raise ErrBadRequest()
    batch = ""
    if kind == "ui":
        first = await session.scalar(
            select(AiGenerationStage)
            .where(
                AiGenerationStage.task_id == task.task_id, AiGenerationStage.stage == "ui_surface"
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        batch = first.source_batch_id or "" if first else ""
    chosen = {}
    for parent in sorted(expected):
        parent_task_id = task.task_id
        if kind == "function" and parent == "feature_understanding":
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
        versions = list(
            (
                await session.scalars(
                    select(AiGenerateStageVersion)
                    .where(
                        AiGenerateStageVersion.task_id == parent_task_id,
                        AiGenerateStageVersion.stage == parent,
                    )
                    .order_by(AiGenerateStageVersion.version_no.desc())
                )
            ).all()
        )
        requested = selected_ids.get(parent)
        if requested:
            match = next((v for v in versions if v.version_id == requested), None)
            if match is None:
                raise dynamic_error(ErrBadRequest, "选择的上游版本不属于当前生成链")
            if kind == "ui" and batch and version_batch(match) != batch:
                raise dynamic_error(ErrBadRequest, "输入已更换，请先基于当前输入重新生成上游阶段")
        else:
            match = next(
                (v for v in versions if kind != "ui" or not batch or version_batch(v) == batch),
                None,
            )
        if match is None:
            raise dynamic_error(ErrBadRequest, f"请先审核通过「{stage_label(kind, parent)}」")
        chosen[parent] = match
    if chosen:
        ids = [v.version_id for v in chosen.values()]
        locked = list(
            (
                await session.scalars(
                    select(AiGenerateStageVersion)
                    .where(AiGenerateStageVersion.version_id.in_(ids))
                    .order_by(AiGenerateStageVersion.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        by_id = {v.version_id: v for v in locked}
        if set(ids) != set(by_id):
            raise dynamic_error(ErrBadRequest, "选择的上游版本已删除，请重新选择")
        chosen = {name: by_id[version.version_id] for name, version in chosen.items()}
    return chosen
