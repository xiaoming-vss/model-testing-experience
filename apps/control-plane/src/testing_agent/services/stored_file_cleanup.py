"""Lease immutable-object deletion and publish receipts with a generation comparison."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.http_diagnostics import safe_exception_trace
from testing_agent.core.object_storage import ObjectStorage, ObjectStorageSettings
from testing_agent.core.sid import new_id
from testing_agent.repositories.file_cleanup import FileCleanupRepository
from testing_agent.services.file_verification import FileVerificationWorkflow
from testing_agent.services.file_verification import now_utc as utcnow

logger = logging.getLogger(__name__)
CLEANUP_LEASE = timedelta(minutes=5)


@dataclass(frozen=True)
class CleanupClaim:
    file_id: str
    generation: str
    bucket: str
    object_key: str
    staging_key: str
    delete_object: bool
    staging_only: bool


class StoredFileCleanup:
    def __init__(
        self, session: AsyncSession, settings: ObjectStorageSettings, storage: ObjectStorage
    ) -> None:
        self.session, self.settings, self.storage = session, settings, storage
        self.repository = FileCleanupRepository(self.session)

    async def claim(self, *, staging: bool, limit: int = 100) -> list[CleanupClaim]:
        now = utcnow()
        rows = await self.repository.candidates(
            self.settings.bucket, now, staging=staging, limit=limit
        )
        preserved = await self.repository.existing_bugs(rows) if not staging else set()
        selected = []
        for row in rows:
            if (
                not staging
                and row.resource_type == "bug"
                and row.status == "deleting"
                and row.completed_at is not None
                and (row.project_id, row.resource_id) in preserved
            ):
                row.status = "archived"
                continue
            if not staging:
                row.status = "deleting"
            row.cleanup_id, row.cleanup_until = new_id(), now + CLEANUP_LEASE
            selected.append(row)
        # New publications never reuse an old object key. Existing legacy references
        # may still share one; retain their object while retiring only this metadata.
        live = (
            await self.repository.live_keys(
                self.settings.bucket, [row.object_key for row in selected]
            )
            if not staging
            else set()
        )
        claims = [
            CleanupClaim(
                row.file_id,
                row.cleanup_id,
                row.bucket,
                row.object_key,
                row.staging_key,
                row.object_key not in live,
                staging,
            )
            for row in selected
        ]
        await self.session.commit()
        return claims

    async def activate(self, claim: CleanupClaim) -> bool:
        # A batch may wait behind slow storage. Recheck ownership immediately before
        # each deletion so an expired queued claim cannot duplicate a new collector.
        row = await self.repository.current(claim.file_id)
        if (
            row is None
            or row.cleanup_id != claim.generation
            or row.bucket != claim.bucket
            or row.staging_key != claim.staging_key
            or (
                not claim.staging_only
                and (row.status != "deleting" or row.object_key != claim.object_key)
            )
        ):
            await self.session.rollback()
            return False
        row.cleanup_until = utcnow() + CLEANUP_LEASE
        await self.session.commit()
        return True

    async def finish(self, claim: CleanupClaim, *, failed: bool = False) -> bool:
        row = await self.repository.current(claim.file_id)
        if row is None or row.cleanup_id != claim.generation or row.bucket != claim.bucket:
            await self.session.rollback()
            return False
        if failed:
            row.cleanup_id, row.cleanup_until = "", None
        elif claim.staging_only:
            if row.staging_key == claim.staging_key:
                row.staging_key = ""
            row.cleanup_id, row.cleanup_until = "", None
        elif row.status == "deleting" and (row.object_key, row.staging_key) == (
            claim.object_key,
            claim.staging_key,
        ):
            await self.session.delete(row)
        else:
            # A changed record never accepts a stale receipt.
            row.cleanup_id, row.cleanup_until = "", None
            await self.session.commit()
            return False
        await self.session.commit()
        return True

    async def run_claims(self, claims: list[CleanupClaim]) -> tuple[int, int]:
        deleted, failed = 0, 0
        for claim in claims:
            try:
                if not await self.activate(claim):
                    continue
                if claim.staging_key:
                    await asyncio.to_thread(self.storage.delete, claim.staging_key)
                if not claim.staging_only and claim.delete_object:
                    await asyncio.to_thread(self.storage.delete, claim.object_key)
                applied = await self.finish(claim)
                if applied and not claim.staging_only:
                    deleted += 1
            except Exception as exc:
                await self.session.rollback()
                failed += 1
                logger.warning(
                    "File cleanup failed file_id=%s error=%s trace=%s; will retry",
                    claim.file_id,
                    type(exc).__name__,
                    safe_exception_trace(exc),
                )
                await self.finish(claim, failed=True)
        return deleted, failed

    async def cleanup(self) -> dict[str, int]:
        try:
            verification = await FileVerificationWorkflow(
                self.session, self.settings, self.storage
            ).collect()
            removed, failed = await self.run_claims(await self.claim(staging=False))
            _, staging_failed = await self.run_claims(await self.claim(staging=True))
            return {
                "deleted": removed + verification["deleted"],
                "failed": failed + staging_failed + verification["failed"],
            }
        except BaseException:
            await self.session.rollback()
            raise
