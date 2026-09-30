"""Task-authorized default-skill files; project custom skills never enter execution."""

from fastapi import Depends, Query
from fastapi.responses import JSONResponse

from testing_agent.api.deps import get_file_service, get_worker_task_service
from testing_agent.core.errors import ErrNotFound
from testing_agent.services.worker_skills import authorized_skill


async def skill_manifest(
    task_id: str,
    name: str,
    worker_id: str = Query(alias="workerId"),
    service=Depends(get_worker_task_service),
):
    skill = await authorized_skill(task_id, name, worker_id, service)
    return JSONResponse(
        {"name": skill.filename, "files": skill.manifest}, headers={"Cache-Control": "no-store"}
    )


async def skill_file(
    task_id: str,
    name: str,
    file_id: str,
    worker_id: str = Query(alias="workerId"),
    service=Depends(get_worker_task_service),
    files=Depends(get_file_service),
):
    skill = await authorized_skill(task_id, name, worker_id, service)
    if not any(entry["fileId"] == file_id for entry in skill.manifest):
        raise ErrNotFound
    row = await files.get(file_id)
    return JSONResponse(await files.ticket(row), headers={"Cache-Control": "no-store"})
