"""Repair legacy names using private copy targets; preserve the original object."""

import asyncio

from sqlalchemy import select

from testing_agent.core.errors import AppError
from testing_agent.core.sid import new_id
from testing_agent.models.file_verification import FileVerification
from testing_agent.models.stored_file import StoredFile
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.file_verification import VERIFY_WINDOW, FileVerificationWorkflow
from testing_agent.services.stored_file import StoredFileService, utcnow


async def repair_file_names(files: StoredFileService, *, apply: bool = False):
    identifiers = list(
        await files.session.scalars(
            select(StoredFile.file_id).where(
                StoredFile.bucket == files.settings.bucket,
                StoredFile.status.in_(["ready", "attached"]),
                StoredFile.object_key.endswith("/content"),
            )
        )
    )
    await files.session.commit()
    results = []
    workflow = FileVerificationWorkflow(files.session, files.settings, files.storage)
    for file_id in identifiers:
        operation_id = ""
        storage_finished = False
        storage_uncertain = False
        try:
            row = await files.get(file_id, lock=apply)
            if row.status not in {"ready", "attached"} or not row.object_key.endswith("/content"):
                await files.session.commit()
                continue
            FileUploadRequest(
                project_id=row.project_id,
                filename=row.filename,
                size=row.size,
                sha256=row.sha256,
                purpose=row.purpose,
            )
            if not apply:
                results.append({"fileId": file_id, "status": "eligible"})
                await files.session.commit()
                continue
            operation_id = new_id()
            source, size, sha256, filename = row.object_key, row.size, row.sha256, row.filename
            new_key = source.rsplit("/", 1)[0] + "/named/" + operation_id + "/" + filename
            if len(new_key) > 512 or len(new_key.encode()) > 1024:
                raise AppError(400, "文件存储路径过长", 400)
            now = utcnow()
            files.session.add(
                FileVerification(
                    operation_id=operation_id,
                    file_id=file_id,
                    bucket=row.bucket,
                    object_key=new_key,
                    state="running",
                    deadline=now + VERIFY_WINDOW,
                    gc_after=now + VERIFY_WINDOW,
                )
            )
            await files.session.commit()
            try:
                await asyncio.to_thread(files.storage.seal, source, new_key, size, sha256, filename)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                storage_finished = True
                storage_uncertain = not isinstance(exc, AppError)
                raise
            storage_finished = True
            current = await files.get(file_id, lock=True)
            operation = await workflow.repository.operation(operation_id)
            if (
                operation is None
                or operation.state != "running"
                or operation.deadline <= utcnow()
                or current.status not in {"ready", "attached"}
                or (current.object_key, current.size, current.sha256) != (source, size, sha256)
            ):
                raise AppError(409, "文件已变化，请重试文件名修复", 409)
            current.object_key = new_key
            operation.state, operation.settled_at = "published", utcnow()
            await files.session.commit()
            results.append({"fileId": file_id, "status": "repaired"})
        except asyncio.CancelledError:
            await files.session.rollback()
            if storage_finished and operation_id:
                await workflow.discard(file_id, operation_id, settled=not storage_uncertain)
            raise
        except Exception as exc:
            await files.session.rollback()
            if storage_finished and operation_id:
                await workflow.discard(file_id, operation_id, settled=not storage_uncertain)
            results.append({"fileId": file_id, "status": "failed", "errorType": type(exc).__name__})
    return results
