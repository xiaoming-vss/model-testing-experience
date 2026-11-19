from fastapi import Depends
from fastapi.responses import JSONResponse

from testing_agent.api.deps import get_ui_worker_artifact_service
from testing_agent.schemas.worker_files import (
    WorkerFileCompleteRequest,
    WorkerFileRequest,
)
from testing_agent.services.ui_worker_artifacts import UiWorkerArtifactService


async def initiate_artifact(
    task_id: str,
    body: WorkerFileRequest,
    artifacts: UiWorkerArtifactService = Depends(get_ui_worker_artifact_service),
):
    ticket = await artifacts.initiate(task_id, body)
    return JSONResponse(ticket, headers={"Cache-Control": "no-store"})


async def complete_artifact(
    task_id: str,
    file_id: str,
    body: WorkerFileCompleteRequest,
    artifacts: UiWorkerArtifactService = Depends(get_ui_worker_artifact_service),
):
    return await artifacts.complete(task_id, file_id, body)
