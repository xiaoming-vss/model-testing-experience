"""Bounded requirement history reads and lightweight task configuration discovery."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.ai_generate_task import AiGenerateTaskRun as Run
from testing_agent.models.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchive as Archive,
)
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.ai_run_history import history_page
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_task_contracts import task_type_for

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
                Archive.filename,
                Archive.file_id,
            )
            .outerjoin(Archive, Archive.task_id == Task.task_id)
            .where(*requirement_scope(requirement_id), Task.task_type.in_(TYPE_KINDS))
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        return [
            {
                "taskId": row.task_id,
                "kind": TYPE_KINDS[row.task_type],
                "name": row.name,
                "sourceType": row.source_type,
                "hasSource": bool(row.file_id)
                if row.task_type == "ui_case_generate"
                else bool(row.has_source),
                "sourceFilename": row.filename or "",
                "createdAt": row.created_at,
                "updatedAt": row.updated_at,
            }
            for row in rows
        ]

    async def run_counts(self, requirement_id: str) -> dict[str, int]:
        rows = await self.session.execute(
            select(Task.task_type, func.count(Run.id))
            .join(Run, Run.task_id == Task.task_id)
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
                    .join(Run, Run.task_id == Task.task_id)
                    .where(
                        *requirement_scope(requirement_id),
                        Task.task_type.in_(TYPE_KINDS),
                        Run.status.in_(RUN_ACTIVE_STATUSES),
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
        return await history_page(
            self.session,
            [*requirement_scope(requirement_id), Task.task_type == task_type_for(kind)],
            page,
            page_size,
            pipeline_filter,
        )
