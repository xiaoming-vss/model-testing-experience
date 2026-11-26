"""Read the current requirement-chain candidate overview."""

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.core.utc import as_utc
from testing_agent.domain.generation_chain import (
    CHAIN_LABELS,
    stage_label,
    stage_names,
    upstream_stages,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.generation_candidate_view import read_candidate_chain_status
from testing_agent.schemas.generation_chain import (
    ChainStageState,
    ChainStageView,
    GenerationChainView,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.stage_storage.module_progress import module_progress_view


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
    candidate_rows = await read_candidate_chain_status(
        session, requirement_id=requirement_id, kind=kind, task_id=task.task_id
    )
    if candidate_rows is None:
        raise dynamic_error(ErrBadRequest, "生成链未绑定候选工作区，请重新创建设置")
    by_stage = {row.stage: row for row in candidate_rows}
    candidate_stages = []
    for index, name in enumerate(stage_names(kind)):
        row = by_stage.get(name)
        state: ChainStageState
        failed_after_adoption = bool(
            row
            and row.last_status in {"failed", "error"}
            and (
                not row.confirmed_at
                or not row.last_attempt_at
                or as_utc(row.last_attempt_at) >= as_utc(row.confirmed_at)
            )
        )
        if row and row.active_attempt_id:
            state = "running"
        elif failed_after_adoption:
            state = "failed"
        elif row and row.current_candidate_id:
            state = "invalid" if row.invalidated_at else "approved"
        elif row and row.candidate_count:
            state = "draft"
        else:
            state = "not_started"
        candidate_stages.append(
            ChainStageView(
                stage=name,
                label=stage_label(kind, name),
                order=index,
                state=state,
                active_run_id=row.active_attempt_id or "" if row else "",
                error_message=row.last_error or "" if row and state == "failed" else "",
                failure_run_id=row.last_attempt_id or "" if row and state == "failed" else "",
                failed_at=row.last_attempt_at if row and state == "failed" else None,
                module_generation=module_progress_view(row.module_attempt) if row else None,
                upstream_stages=list(upstream_stages(kind, name)),
            )
        )
    active = any(row.active_attempt_id for row in candidate_rows)
    return GenerationChainView(
        kind=kind,
        label=CHAIN_LABELS[kind],
        configured=True,
        candidate_mode=True,
        task_id=task.task_id,
        active=active,
        busy=active,
        pending_candidate_count=sum(
            max(0, row.candidate_count - int(bool(row.current_candidate_id)))
            for row in candidate_rows
        ),
        stages=candidate_stages,
    )
