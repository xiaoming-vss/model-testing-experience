"""Authorize current default skill access for the active worker execution."""

from datetime import UTC, datetime

from testing_agent.core.errors import AppError, ErrForbidden, ErrNotFound


async def authorized_skill(task_id, name, worker_id, service):
    task = await service.ai_worker_task(task_id)
    lease = task.lease_expires_at
    if (
        task.worker_id != worker_id
        or task.status not in {"claimed", "running"}
        or lease is None
        or lease.replace(tzinfo=UTC) <= datetime.now(UTC)
    ):
        raise ErrForbidden()
    skill = await service.repository.default_skill(name)
    if skill is None:
        raise AppError(409, f"缺少系统默认 Skill: {name}", 409)
    return skill


async def authorized_skill_ticket(task_id, name, file_id, worker_id, service, files):
    """Authorize the task lease and skill manifest before issuing a file ticket."""
    skill = await authorized_skill(task_id, name, worker_id, service)
    if not any(entry["fileId"] == file_id for entry in skill.manifest):
        raise ErrNotFound()
    row = await files.get(file_id)
    return await files.ticket(row)
