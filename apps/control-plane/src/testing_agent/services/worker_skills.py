"""Authorize current default skill access for the active worker execution."""

from datetime import UTC, datetime

from sqlalchemy import select

from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.models.project_skill_space import ProjectSkillSpace


async def authorized_skill(task_id, name, worker_id, service):
    task = await service._ai_worker_task(task_id)
    lease = task.lease_expires_at
    if (
        task.worker_id != worker_id
        or task.status not in {"claimed", "running"}
        or lease is None
        or lease.replace(tzinfo=UTC) <= datetime.now(UTC)
    ):
        raise ErrForbidden()
    skill = await service.repository.session.scalar(
        select(ProjectSkillSpace).where(
            ProjectSkillSpace.is_default.is_(True), ProjectSkillSpace.filename == name
        )
    )
    if skill is None:
        raise AppError(409, f"缺少系统默认 Skill: {name}", 409)
    return skill
