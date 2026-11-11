"""Bounded requirement history reads and lightweight task configuration discovery."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt as Attempt
from testing_agent.models.ai_generation_stage import AiGenerationStage as Stage
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.schemas.requirement_design import DesignKind

KINDS: tuple[DesignKind, ...] = ("requirement_analysis", "function", "api", "ui")
TYPE_KINDS = {task_type_for(kind): kind for kind in KINDS}


def requirement_scope(requirement_id: str):
    # Reject malformed legacy task links as well as new cross-project links.
    sprint_id = (
        select(Requirement.sprint_id)
        .where(Requirement.requirement_id == requirement_id)
        .scalar_subquery()
    )
    project_id = (
        select(Sprint.project_id)
        .join(Requirement, Requirement.sprint_id == Sprint.sprint_id)
        .where(Requirement.requirement_id == requirement_id)
        .scalar_subquery()
    )
    return [
        Task.requirement_id == requirement_id,
        (Task.sprint_id == sprint_id) | (Task.sprint_id == ""),
        Task.project_id == project_id,
    ]


class RequirementDesignRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def configuration_task_id(self, requirement_id: str, kind: DesignKind) -> str | None:
        # Current read after the parent lock: a REPEATABLE READ snapshot opened
        # during authorization must not hide a concurrent request's new task.
        return await self.session.scalar(
            select(Task.task_id)
            .where(*requirement_scope(requirement_id), Task.task_type == task_type_for(kind))
            .order_by(Task.created_at.desc(), Task.id.desc())
            .limit(1)
            .with_for_update()
        )

    async def task_summaries(self, requirement_id: str) -> list[dict[str, Any]]:
        rows = await self.session.execute(
            select(
                Task.task_id,
                Task.task_type,
                Task.name,
                Task.source_type,
                (func.length(Task.source_content) > 0).label("has_source"),
                Task.created_at,
                Task.updated_at,
            )
            .where(*requirement_scope(requirement_id), Task.task_type.in_(TYPE_KINDS))
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        return [
            {
                "taskId": row.task_id,
                "kind": TYPE_KINDS[row.task_type],
                "name": row.name,
                "sourceType": row.source_type,
                "hasSource": bool(row.has_source),
                "sourceFilename": "",
                "createdAt": row.created_at,
                "updatedAt": row.updated_at,
            }
            for row in rows
        ]

    async def run_counts(self, requirement_id: str) -> dict[str, int]:
        rows = await self.session.execute(
            select(Task.task_type, func.count(Attempt.id))
            .join(Stage, Stage.task_id == Task.task_id)
            .join(Attempt, Attempt.stage_id == Stage.id)
            .where(*requirement_scope(requirement_id), Task.task_type.in_(TYPE_KINDS))
            .group_by(Task.task_type)
        )
        counts: dict[str, int] = {kind: 0 for kind in KINDS}
        counts.update({TYPE_KINDS[row[0]]: row[1] for row in rows})
        return counts

    async def active_task_ids(self, requirement_id: str) -> list[str]:
        from testing_agent.core.enums import RUN_ACTIVE_STATUSES

        return list(
            (
                await self.session.scalars(
                    select(Task.task_id)
                    .join(Stage, Stage.task_id == Task.task_id)
                    .join(Attempt, Attempt.stage_id == Stage.id)
                    .where(
                        *requirement_scope(requirement_id),
                        Task.task_type.in_(TYPE_KINDS),
                        Attempt.status.in_(RUN_ACTIVE_STATUSES),
                    )
                    .distinct()
                )
            ).all()
        )

    async def history(
        self,
        requirement_id: str,
        kind: DesignKind,
        page: int,
        page_size: int,
        pipeline_filter: str,
    ) -> dict[str, Any]:
        from testing_agent.domain.direct_history_projection import project_direct_history
        from testing_agent.repositories.direct_attempt_history import direct_history_rows

        rows = await direct_history_rows(
            self.session,
            None,
            page,
            page_size,
            pipeline_filter,
            task_conditions=(
                *requirement_scope(requirement_id),
                Task.task_type == task_type_for(kind),
            ),
        )
        return project_direct_history(*rows)
