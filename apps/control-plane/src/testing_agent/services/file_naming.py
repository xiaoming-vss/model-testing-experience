"""Repair legacy final object names without deleting existing objects or links."""

import asyncio

from sqlalchemy import select

from testing_agent.models.stored_file import StoredFile
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.stored_file import StoredFileService


async def repair_file_names(files: StoredFileService, *, apply: bool = False):
    identifiers = list(
        (
            await files.session.scalars(
                select(StoredFile.file_id).where(
                    StoredFile.status.in_(["ready", "attached"]),
                    StoredFile.object_key.endswith("/content"),
                )
            )
        ).all()
    )
    results = []
    for file_id in identifiers:
        try:
            row = await files.get(file_id, lock=apply)
            if row.status not in {"ready", "attached"} or not row.object_key.endswith("/content"):
                continue
            # Validate historical names before using them as object keys or response headers.
            FileUploadRequest(
                project_id=row.project_id,
                filename=row.filename,
                size=row.size,
                sha256=row.sha256,
                purpose=row.purpose,
            )
            new_key = row.object_key.rsplit("/", 1)[0] + "/" + row.filename
            if not apply:
                results.append({"fileId": file_id, "status": "eligible"})
                continue
            await asyncio.to_thread(
                files.storage.seal, row.object_key, new_key, row.size, row.sha256, row.filename
            )
            row.object_key = new_key
            await files.session.commit()
            results.append({"fileId": file_id, "status": "repaired"})
        except Exception as exc:
            await files.session.rollback()
            results.append({"fileId": file_id, "status": "failed", "errorType": type(exc).__name__})
    return results
