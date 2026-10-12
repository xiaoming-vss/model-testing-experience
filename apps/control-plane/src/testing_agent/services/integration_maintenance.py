"""Bounded history compaction; never discard write evidence or step result receipts.

Claim-receipt ledger rows age out after ``claim_receipt_retention_days`` (or once
their job is archived): replaying a claim request after that window is treated as
a new request. Step-level operation ids and result receipts are kept forever.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, func, or_, select

from testing_agent.domain.integration_execution import utc
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_job import (
    IntegrationClaimReceipt,
    IntegrationJob,
    IntegrationJobStep,
)
from testing_agent.models.project import Project
from testing_agent.repositories.integration_job import IntegrationJobRepository

TERMINAL = ("succeeded", "partial", "failed", "canceled")


class IntegrationHistoryMaintenance:
    def __init__(self, session, settings, *, clock=lambda: datetime.now(UTC)):
        self.session, self.settings, self.clock = session, settings, clock
        self.repository = IntegrationJobRepository(session)

    def candidates(self):
        now = self.clock()
        success_cutoff = now - timedelta(days=self.settings.succeeded_retention_days)
        failure_cutoff = now - timedelta(days=self.settings.failed_retention_days)
        unresolved = exists(
            select(IntegrationJobStep.id).where(
                IntegrationJobStep.job_id == IntegrationJob.job_id,
                IntegrationJobStep.status.in_(["pending", "write_intent", "unknown"]),
            )
        )
        current_push = exists(
            select(BugZentaoPush.id)
            .where(
                BugZentaoPush.bug_id == IntegrationJob.bug_id,
                or_(
                    BugZentaoPush.operation_id == IntegrationJobStep.operation_id,
                    BugZentaoPush.description_operation_id == IntegrationJobStep.operation_id,
                    BugZentaoPush.payload_json["_fieldUpdate"]["operationId"].as_string()
                    == IntegrationJobStep.operation_id,
                ),
            )
            .correlate(IntegrationJob, IntegrationJobStep)
        )
        current_file = exists(
            select(BugZentaoAttachment.id)
            .where(
                BugZentaoAttachment.bug_id == IntegrationJob.bug_id,
                BugZentaoAttachment.operation_id == IntegrationJobStep.operation_id,
            )
            .correlate(IntegrationJob, IntegrationJobStep)
        )
        referenced = exists(
            select(IntegrationJobStep.id).where(
                IntegrationJobStep.job_id == IntegrationJob.job_id,
                IntegrationJobStep.operation_id != "",
                or_(current_push, current_file),
            )
        )
        return select(IntegrationJob.job_id).where(
            IntegrationJob.archived_at.is_(None),
            IntegrationJob.recovery_required.is_(False),
            IntegrationJob.active_scope.is_(None),
            IntegrationJob.active_target.is_(None),
            or_(
                (IntegrationJob.status == "succeeded")
                & (IntegrationJob.finished_at < success_cutoff),
                IntegrationJob.status.in_(["partial", "failed", "canceled"])
                & (IntegrationJob.finished_at < failure_cutoff),
            ),
            ~unresolved,
            ~referenced,
        )

    async def protected(self, job, steps):
        """Recheck current locked facts after the candidate query, including RR snapshots."""
        cutoff = self.clock() - timedelta(
            days=self.settings.succeeded_retention_days
            if job.status == "succeeded"
            else self.settings.failed_retention_days
        )
        if (
            job.status not in TERMINAL
            or job.recovery_required
            or job.archived_at is not None
            or job.active_scope is not None
            or job.active_target is not None
            or job.finished_at is None
            or utc(job.finished_at) >= cutoff
            or any(s.status in ("pending", "write_intent", "unknown") for s in steps)
        ):
            return True
        row = await self.session.scalar(
            select(BugZentaoPush)
            .where(BugZentaoPush.bug_id == job.bug_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        operations = {s.operation_id for s in steps if s.operation_id}
        if row is not None and operations.intersection(
            {
                row.operation_id,
                row.description_operation_id,
                row.payload_json.get("_fieldUpdate", {}).get("operationId", ""),
            }
        ):
            return True
        files = (
            await self.session.scalars(
                select(BugZentaoAttachment)
                .where(BugZentaoAttachment.bug_id == job.bug_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        return any(file.operation_id in operations for file in files)

    async def compact(self):
        identifiers = (
            await self.session.scalars(
                self.candidates()
                .order_by(IntegrationJob.project_id, IntegrationJob.id)
                .limit(self.settings.maintenance_batch_size)
            )
        ).all()
        compacted = 0
        for job_id in identifiers:
            candidate = await self.repository.get(job_id)
            if candidate is None:
                continue
            await self.session.scalar(
                select(Project)
                .where(Project.project_id == candidate.project_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            job = await self.repository.get(job_id, lock=True)
            if job is None:
                continue
            steps = await self.repository.steps(job_id, lock=True)
            if await self.protected(job, steps):
                continue
            # Keep request identity/digests and immutable result receipts indefinitely.
            # Old submissions/results can be recognized, but cannot start another write.
            job.snapshot_json = (
                {"clientRequest": job.snapshot_json["clientRequest"]}
                if "clientRequest" in job.snapshot_json
                else {}
            )
            job.mapping_json = {}
            for step in steps:
                step.input_json = {}
            job.archived_at = self.clock()
            compacted += 1
        pruned_receipts = await self.prune_claim_receipts()
        await self.session.flush()
        backlog = await self.session.scalar(
            select(func.count()).select_from(self.candidates().subquery())
        )
        return {
            "compacted": compacted,
            "backlog": backlog,
            "prunedReceipts": pruned_receipts,
        }

    async def prune_claim_receipts(self):
        """Drop claim receipts past the retention window or pointing at archived jobs."""
        cutoff = self.clock() - timedelta(days=self.settings.claim_receipt_retention_days)
        archived_job = exists(
            select(IntegrationJob.job_id).where(
                IntegrationJob.job_id == IntegrationClaimReceipt.job_id,
                IntegrationJob.archived_at.is_not(None),
            )
        )
        identifiers = (
            await self.session.scalars(
                select(IntegrationClaimReceipt.claim_key)
                .where(
                    or_(IntegrationClaimReceipt.created_at < cutoff, archived_job),
                )
                .order_by(IntegrationClaimReceipt.created_at, IntegrationClaimReceipt.claim_key)
                .limit(self.settings.maintenance_batch_size)
            )
        ).all()
        if identifiers:
            await self.session.execute(
                delete(IntegrationClaimReceipt).where(
                    IntegrationClaimReceipt.claim_key.in_(identifiers)
                )
            )
        return len(identifiers)
