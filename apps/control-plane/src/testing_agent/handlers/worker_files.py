from fastapi import Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.api.deps import get_file_service, get_worker_task_service
from testing_agent.core.errors import ErrForbidden
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.worker import find_task
from testing_agent.services.worker_authorization import authorize_execution
from testing_agent.services.worker_task import ensure_worker_match


class WorkerFileRequest(BaseModel):
    worker_id: str
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00-\x1f]+$")
    size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerFileCompleteRequest(BaseModel):
    worker_id: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


async def authority(service, task_id, worker_id):
    task = await find_task(service.repository.session, "ui", task_id)
    ensure_worker_match(task, worker_id)
    return await authorize_execution(service.repository.session, task)


async def initiate_artifact(
    task_id: str,
    body: WorkerFileRequest,
    service=Depends(get_worker_task_service),
    files=Depends(get_file_service),
):
    actor = await authority(service, task_id, body.worker_id)
    ticket = await files.initiate(
        actor.actor,
        FileUploadRequest(
            project_id=actor.project_id,
            filename=body.filename,
            size=body.size,
            sha256=body.sha256,
            purpose="ui_artifact",
        ),
        resource_type="ui_worker_task",
        resource_id=task_id,
    )
    return JSONResponse(ticket, headers={"Cache-Control": "no-store"})


async def complete_artifact(
    task_id: str,
    file_id: str,
    body: WorkerFileCompleteRequest,
    service=Depends(get_worker_task_service),
    files=Depends(get_file_service),
):
    actor = await authority(service, task_id, body.worker_id)
    row = await files.get(file_id)
    if (row.resource_type, row.resource_id, row.project_id, row.uploaded_by, row.purpose) != (
        "ui_worker_task",
        task_id,
        actor.project_id,
        actor.actor,
        "ui_artifact",
    ):
        raise ErrForbidden()
    await files.complete(actor.actor, file_id)
    # Verification releases its transaction; the task may have lost its lease meanwhile.
    actor = await authority(service, task_id, body.worker_id)
    await files.attach(
        actor.actor, file_id, actor.project_id, "ui_worker_task", task_id, purpose="ui_artifact"
    )
    await files.session.commit()
    return {"fileId": file_id, "path": f"/v1/files/{file_id}/download"}
