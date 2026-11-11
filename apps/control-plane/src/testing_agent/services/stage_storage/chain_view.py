"""full requirement-chain view from direct stage storage."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_chain import (
    CHAIN_LABELS,
    stage_label,
    stage_names,
    upstream_stages,
)
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_chain import (
    ChainLeafView,
    ChainSourceInputsView,
    ChainStageView,
    GenerationChainView,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.stage_storage.views import attempt_source, build_stage_views
from testing_agent.services.ui_generation_sources import ui_source_inputs


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def build_chain_view(
    session: AsyncSession,
    requirement_id: str,
    kind: DesignKind,
    task: AiGenerateTask | None,
    *,
    detail: bool,
) -> GenerationChainView:
    """Caller validates requirement and task access before calling this function."""
    if task is None:
        return GenerationChainView(
            kind=kind,
            label=CHAIN_LABELS[kind],
            configured=False,
            stages=[
                ChainStageView(
                    stage=name,
                    label=stage_label(kind, name),
                    order=index,
                    state="not_started",
                    upstream_stages=list(upstream_stages(kind, name)),
                )
                for index, name in enumerate(stage_names(kind))
            ],
        )
    direct = await build_stage_views(session, task, kind, detail=detail)
    stages = list(
        (
            await session.scalars(
                select(AiGenerationStage).where(AiGenerationStage.task_id == task.task_id)
            )
        ).all()
    )
    attempts = (
        list(
            (
                await session.scalars(
                    select(AiGenerationAttempt)
                    .where(AiGenerationAttempt.stage_id.in_([row.id for row in stages]))
                    .order_by(AiGenerationAttempt.created_at, AiGenerationAttempt.id)
                )
            ).all()
        )
        if stages
        else []
    )
    versions = list(
        (
            await session.scalars(
                select(AiGenerateStageVersion).where(AiGenerateStageVersion.task_id == task.task_id)
            )
        ).all()
    )
    latest = attempts[-1] if attempts else None
    by_id = {attempt.id: attempt for attempt in attempts}
    first = next((row for row in stages if row.stage == stage_names(kind)[0]), None)
    first_attempt = (
        by_id.get((first.active_attempt_id or first.current_attempt_id) or "") if first else None
    )
    source = (
        (first.source_snapshot_json or attempt_source(first_attempt))
        if kind == "ui" and first
        else attempt_source(latest)
    )
    requirement = await session.scalar(
        select(Requirement).where(Requirement.requirement_id == requirement_id)
    )
    source_changed = bool(
        requirement
        and source.get("documentHash")
        and requirement.document_hash
        and source.get("documentHash") != requirement.document_hash
    )
    if kind == "ui" and first and (first.source_batch_id or first_attempt):
        cases = source.get("functionalCases") or []
        ids = [case["caseId"] for case in cases if isinstance(case, dict) and "caseId" in case]
        current = (
            await AiGenerateTaskRepository(session).list_ui_source_cases(requirement_id, ids)
            if ids
            else []
        )
        # Repository drift needs an explicit source-check; chain reads only
        # verify the frozen formal case content.
        source_changed = current != cases
    leaf_stage = direct.stages[-1]
    leaf_version_id = leaf_stage.latest_version.version_id if leaf_stage.latest_version else ""
    imports = (
        list(
            (
                await session.scalars(
                    select(AiGenerateVersionImport).where(
                        AiGenerateVersionImport.task_id == task.task_id,
                        AiGenerateVersionImport.version_id == leaf_version_id,
                    )
                )
            ).all()
        )
        if leaf_version_id
        else []
    )
    targets = []
    seen = set()
    for item in imports:
        key = (item.target_type, item.target_id)
        if key not in seen:
            seen.add(key)
            targets.append({"targetType": item.target_type, "targetId": item.target_id})
    dates = [_aware(attempt.created_at) for attempt in attempts] + [
        _aware(version.reviewed_at or version.created_at) for version in versions
    ]
    source_inputs = ui_source_inputs(source) if kind == "ui" and detail else None
    return GenerationChainView(
        kind=kind,
        label=CHAIN_LABELS[kind],
        configured=True,
        task_id=task.task_id,
        run_id=latest.id if latest else "",
        source_batch_id=direct.source_batch_id,
        active=direct.busy,
        busy=direct.busy,
        source_changed=source_changed,
        source_inputs=ChainSourceInputsView.model_validate(source_inputs)
        if source_inputs
        else None,
        updated_at=max((value for value in dates if value), default=None),
        draft_count=direct.draft_count,
        stages=direct.stages,
        leaf=ChainLeafView(
            stage=leaf_stage.stage if leaf_version_id else "",
            version_id=leaf_version_id,
            version_no=leaf_stage.latest_version.version_no if leaf_stage.latest_version else 0,
            imported=bool(imports),
            imported_targets=targets,
            imported_at=max(
                (value for item in imports if (value := _aware(item.imported_at))), default=None
            ),
        ),
    )
