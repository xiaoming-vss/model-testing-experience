from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select

from testing_agent.models.integration_job import (
    IntegrationClaimReceipt,
    IntegrationJob,
    IntegrationJobStep,
)
from testing_agent.repositories.base import BaseRepository


class IntegrationJobRepository(BaseRepository):
    async def get(
        self, job_id: str, *, lock: bool = False, skip_locked: bool = False
    ) -> IntegrationJob | None:
        query = select(IntegrationJob).where(IntegrationJob.job_id == job_id)
        if lock:
            query = query.with_for_update(skip_locked=skip_locked).execution_options(
                populate_existing=True
            )
        return await self.session.scalar(query)

    async def by_request(
        self, actor: str, request_id: str, *, lock: bool = False
    ) -> IntegrationJob | None:
        query = select(IntegrationJob).where(
            IntegrationJob.actor_user_id == actor, IntegrationJob.request_id == request_id
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(query)

    async def claim_receipt(
        self, claim_key: str, *, lock: bool = False
    ) -> IntegrationClaimReceipt | None:
        query = select(IntegrationClaimReceipt).where(
            IntegrationClaimReceipt.claim_key == claim_key
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(query)

    async def candidate(
        self,
        versions: Sequence[int],
        types: Sequence[str],
        excluded: list[int],
        *,
        lock: bool = True,
    ) -> IntegrationJob | None:
        # Lock exact primary-key rows. A range lock on the queue index in MySQL's
        # REPEATABLE READ can block another claimant's status/index update.
        identifiers = (
            await self.session.scalars(
                select(IntegrationJob.id)
                .where(
                    IntegrationJob.status == "queued",
                    IntegrationJob.recovery_required.is_(False),
                    IntegrationJob.protocol_version.in_(versions),
                    IntegrationJob.task_type.in_(types),
                    IntegrationJob.id.not_in(excluded),
                )
                .order_by(IntegrationJob.created_at, IntegrationJob.id)
                .limit(100)
            )
        ).all()
        for identifier in identifiers:
            query = select(IntegrationJob)
            query = query.where(
                IntegrationJob.id == identifier,
                IntegrationJob.status == "queued",
                IntegrationJob.recovery_required.is_(False),
            )
            if lock:
                query = query.with_for_update(skip_locked=True)
            job = await self.session.scalar(query.execution_options(populate_existing=True))
            if job is not None:
                return job
        return None

    async def target_busy(self, target_key: str) -> bool:
        return (
            await self.session.scalar(
                select(IntegrationJob.id).where(IntegrationJob.active_target == target_key).limit(1)
            )
            is not None
        )

    async def steps(self, job_id: str, *, lock: bool = False) -> list[IntegrationJobStep]:
        query = (
            select(IntegrationJobStep)
            .where(IntegrationJobStep.job_id == job_id)
            .order_by(IntegrationJobStep.id)
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return list((await self.session.scalars(query)).all())

    async def expired(
        self, now: datetime, limit: int = 100, *, lock: bool = True
    ) -> list[IntegrationJob]:
        query = (
            select(IntegrationJob)
            .where(
                IntegrationJob.status.in_(["claimed", "running"]),
                IntegrationJob.lease_expires_at <= now,
            )
            .order_by(IntegrationJob.lease_expires_at, IntegrationJob.id)
            .limit(limit)
        )
        if lock:
            query = query.with_for_update(skip_locked=True)
        return list(
            (await self.session.scalars(query.execution_options(populate_existing=True))).all()
        )

    async def matching(
        self,
        *,
        project_id: str | None = None,
        bug_id: str | None = None,
        actor_user_id: str | None = None,
        service_id: str | None = None,
        connection_id: str | None = None,
        lock: bool = True,
    ) -> list[IntegrationJob]:
        query = select(IntegrationJob).where(
            IntegrationJob.status.in_(["queued", "claimed", "running"])
        )
        for field, value in {
            "project_id": project_id,
            "bug_id": bug_id,
            "actor_user_id": actor_user_id,
            "service_id": service_id,
            "connection_id": connection_id,
        }.items():
            if value is not None:
                query = query.where(getattr(IntegrationJob, field) == value)
        query = query.order_by(IntegrationJob.project_id, IntegrationJob.id)
        if lock:
            query = query.with_for_update()
        return list(
            (await self.session.scalars(query.execution_options(populate_existing=True))).all()
        )

    async def latest(self, bug_id: str) -> IntegrationJob | None:
        return await self.session.scalar(
            select(IntegrationJob)
            .where(IntegrationJob.bug_id == bug_id)
            .order_by(IntegrationJob.id.desc())
            .limit(1)
        )

    async def active(self, bug_id: str) -> IntegrationJob | None:
        return await self.session.scalar(
            select(IntegrationJob)
            .where(IntegrationJob.bug_id == bug_id, IntegrationJob.active_scope.is_not(None))
            .limit(1)
        )
