"""requirement-chain stage views from the direct stage ledger."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_chain import (
    artifact_summary,
    stage_label,
    stage_names,
    upstream_stages,
)
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.schemas.generation_chain import (
    ChainSourceInputsView,
    ChainStageDraftView,
    ChainStageState,
    ChainStageVersionSummary,
    ChainStageView,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.stage_storage.module_progress import module_progress_view
from testing_agent.services.ui_generation_sources import ui_source_inputs


@dataclass(frozen=True)
class DirectStageViews:
    stages: list[ChainStageView]
    draft_count: int
    busy: bool
    source_batch_id: str


def attempt_source(attempt: AiGenerationAttempt | None) -> dict[str, Any]:
    if attempt is None:
        return {}
    snapshot = attempt.input_snapshot_json or {}
    source = snapshot.get("source") if isinstance(snapshot, dict) else None
    return source if isinstance(source, dict) else {}


def _batch(attempt: AiGenerationAttempt | None) -> str:
    if attempt is None:
        return ""
    return str(attempt_source(attempt).get("uiSourceBatchId") or attempt.id)


def version_batch(version: AiGenerateStageVersion) -> str:
    return str((version.artifact_context_json or {}).get("uiSourceBatchId") or version.attempt_id)


async def build_stage_views(
    session: AsyncSession, task: AiGenerateTask, kind: DesignKind, *, detail: bool
) -> DirectStageViews:
    """Build the stage section without reading old run, run-stage or attempt tables."""
    stage_rows = list(
        (
            await session.scalars(
                select(AiGenerationStage).where(AiGenerationStage.task_id == task.task_id)
            )
        ).all()
    )
    by_name = {row.stage: row for row in stage_rows}
    attempt_rows = (
        list(
            (
                await session.scalars(
                    select(AiGenerationAttempt)
                    .where(AiGenerationAttempt.stage_id.in_([row.id for row in stage_rows]))
                    .order_by(AiGenerationAttempt.attempt_no)
                )
            ).all()
        )
        if stage_rows
        else []
    )
    attempts = {row.id: row for row in attempt_rows}
    grouped_attempts: dict[str, list[AiGenerationAttempt]] = defaultdict(list)
    for attempt in attempt_rows:
        grouped_attempts[attempt.stage_id].append(attempt)
    versions = list(
        (
            await session.scalars(
                select(AiGenerateStageVersion)
                .where(AiGenerateStageVersion.task_id == task.task_id)
                .order_by(AiGenerateStageVersion.version_no)
            )
        ).all()
    )
    by_stage: dict[str, list[AiGenerateStageVersion]] = defaultdict(list)
    for version in versions:
        by_stage[version.stage].append(version)
    imported = set(
        (
            await session.scalars(
                select(AiGenerateVersionImport.version_id).where(
                    AiGenerateVersionImport.task_id == task.task_id
                )
            )
        ).all()
    )
    ui_first = by_name.get("ui_surface") if kind == "ui" else None
    first_attempt = (
        attempts.get((ui_first.active_attempt_id or ui_first.current_attempt_id) or "")
        if ui_first
        else None
    )
    source_batch = (ui_first.source_batch_id or _batch(first_attempt)) if ui_first else ""
    current_latest = {
        stage: matches[-1]
        for stage, candidates in by_stage.items()
        if (
            matches := [
                version
                for version in candidates
                if kind != "ui" or not source_batch or version_batch(version) == source_batch
            ]
        )
    }
    if kind == "function":
        upstream_task = await session.scalar(
            select(AiGenerateTask)
            .where(
                AiGenerateTask.requirement_id == task.requirement_id,
                AiGenerateTask.task_type == "requirement_analysis",
            )
            .order_by(AiGenerateTask.created_at.desc(), AiGenerateTask.id.desc())
            .limit(1)
        )
        if upstream_task is not None:
            upstream = await session.scalar(
                select(AiGenerateStageVersion)
                .where(
                    AiGenerateStageVersion.task_id == upstream_task.task_id,
                    AiGenerateStageVersion.stage == "extracting_text",
                )
                .order_by(AiGenerateStageVersion.version_no.desc())
                .limit(1)
            )
            if upstream is not None:
                current_latest["extracting_text"] = upstream
    views: list[ChainStageView] = []
    draft_count = 0
    busy = False
    for order, name in enumerate(stage_names(kind)):
        stage = by_name.get(name)
        candidates = by_stage[name]
        latest = candidates[-1] if candidates else None
        active = attempts.get(stage.active_attempt_id or "") if stage else None
        current = attempts.get(stage.current_attempt_id or "") if stage else None
        last = grouped_attempts[stage.id][-1] if stage and grouped_attempts[stage.id] else None
        state = (
            "approved"
            if latest and (name in current_latest or (kind == "ui" and name == "ui_yaml"))
            else "invalid"
            if latest
            else "not_started"
        )
        if active and active.status in {"pending", "claimed", "running"}:
            state = "running"
            busy = True
        draft = None
        if (
            stage
            and stage.review_status in {"pending", "approved"}
            and current
            and current.status == "success"
            and current.output_content
            and current.id not in {row.attempt_id for row in candidates}
            and current.invalidated_reason != "审核未通过，候选产物已丢弃"
        ):
            snapshot = current.input_snapshot_json or {}
            versioning = snapshot.get("versioning") if isinstance(snapshot, dict) else None
            versioning = versioning if isinstance(versioning, dict) else {}
            base_id = str(versioning.get("baseVersionId") or (latest.version_id if latest else ""))
            base = next((v for v in candidates if v.version_id == base_id), latest)
            source_inputs = (
                ui_source_inputs(attempt_source(current)) if kind == "ui" and detail else None
            )
            draft = ChainStageDraftView(
                attempt_id=current.id,
                run_id=current.id,
                status="invalidated" if current.invalidated_at else "draft",
                summary=artifact_summary(name, current.output_content, current.output_format),
                artifact_format=current.output_format or "text",
                content=current.output_content if detail else "",
                revision=current.attempt_no,
                base_version_id=base_id,
                base_version_label=f"v{base.version_no}" if base else "",
                upstream_versions={
                    k: v
                    for k, v in (versioning.get("upstreamVersions") or {}).items()
                    if isinstance(v, str)
                },
                source_inputs=ChainSourceInputsView.model_validate(source_inputs)
                if source_inputs
                else None,
                instruction=current.revision_instruction or "",
                invalidated=bool(current.invalidated_at),
                invalidated_reason=current.invalidated_reason or "",
                created_at=current.created_at,
            )
            if not draft.invalidated:
                draft_count += 1
                if state != "running":
                    state = "draft"
            elif latest is None and state != "running":
                state = "invalid"
        failed = (
            last
            if last
            and last.status in {"failed", "error"}
            and (not draft or last.id != draft.attempt_id)
            else None
        )
        if failed is not None:
            state = "failed"
        summaries = [
            ChainStageVersionSummary(
                version_id=v.version_id,
                stage=name,
                stage_label=stage_label(kind, name),
                version_no=v.version_no,
                label=f"v{v.version_no}",
                summary=artifact_summary(name, v.artifact_content, v.artifact_format),
                artifact_format=v.artifact_format,
                created_at=v.reviewed_at or v.created_at,
                reviewer_user_id=v.reviewer_user_id,
                source_run_id=v.attempt_id,
                source_batch_id=version_batch(v) if kind == "ui" else "",
                imported=v.version_id in imported,
            )
            for v in reversed(candidates)
        ]
        if (
            latest
            and latest.version_id in imported
            and name == stage_names(kind)[-1]
            and name in current_latest
        ):
            state = "imported"
        blocked = next(
            (
                f"请先审核通过「{stage_label(kind, parent)}」"
                for parent in upstream_stages(kind, name)
                if parent not in current_latest
            ),
            "",
        )
        views.append(
            ChainStageView(
                stage=name,
                label=stage_label(kind, name),
                order=order,
                state=cast(ChainStageState, state),
                latest_version=summaries[0] if summaries else None,
                draft=draft,
                versions=summaries,
                upstream_stages=list(upstream_stages(kind, name)),
                blocked_reason=blocked,
                error_message=(failed.error_message or "") if failed else "",
                failure_run_id=failed.id if failed else "",
                failed_at=(failed.finished_at or failed.created_at) if failed else None,
                active_run_id=active.id if active and state == "running" else "",
                module_generation=module_progress_view(active or last)
                if name in {"detailed_cases", "case_names"}
                else None,
            )
        )
    return DirectStageViews(views, draft_count, busy, source_batch)
