"""UI Worker artifact upload commands.

The worker gateway binds an upload to the current authorized execution, verifies
the object, and attaches it to the same task. HTTP handlers only translate the
request and response; authority rechecks and the attaching transaction live here
so the handler never touches a database session.
"""

from testing_agent.core.errors import ErrForbidden
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.schemas.worker_files import (
    WorkerFileCompleteRequest,
    WorkerFileRequest,
)
from testing_agent.services.stored_file import StoredFileService
from testing_agent.services.worker_authorization import ExecutionAuthority
from testing_agent.services.worker_task import WorkerTaskService


class UiWorkerArtifactService:
    def __init__(self, tasks: WorkerTaskService, files: StoredFileService):
        self.tasks = tasks
        self.files = files

    async def _authority(self, task_id: str, worker_id: str) -> ExecutionAuthority:
        return await self.tasks.ui_artifact_authority(task_id, worker_id)

    async def initiate(self, task_id: str, body: WorkerFileRequest) -> dict:
        actor = await self._authority(task_id, body.worker_id)
        return await self.files.initiate(
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

    async def complete(self, task_id: str, file_id: str, body: WorkerFileCompleteRequest) -> dict:
        actor = await self._authority(task_id, body.worker_id)
        row = await self.files.get(file_id)
        if (
            row.resource_type,
            row.resource_id,
            row.project_id,
            row.uploaded_by,
            row.purpose,
        ) != (
            "ui_worker_task",
            task_id,
            actor.project_id,
            actor.actor,
            "ui_artifact",
        ):
            raise ErrForbidden()
        await self.files.complete(actor.actor, file_id)
        # Verification releases its transaction; the task may have lost its lease meanwhile.
        actor = await self._authority(task_id, body.worker_id)
        await self.files.attach(
            actor.actor,
            file_id,
            actor.project_id,
            "ui_worker_task",
            task_id,
            purpose="ui_artifact",
        )
        await self.files.session.commit()
        return {"fileId": file_id, "path": f"/v1/files/{file_id}/download"}
