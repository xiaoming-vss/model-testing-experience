"""Local capability contact and bounded SQL aggregates; no execution authorization."""

import json
from datetime import timedelta
from typing import cast

from sqlalchemy import Table, case, exists, func, or_, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.sql.elements import ColumnElement

from testing_agent.domain.integration_execution import utc
from testing_agent.models.integration_job import (
    IntegrationJob,
    IntegrationJobStep,
    IntegrationWorkerPresence,
)
from testing_agent.repositories.base import BaseRepository


class IntegrationObservationRepository(BaseRepository):
    async def contact(self, body, generation, now):
        worker = cast(Table, IntegrationWorkerPresence.__table__)
        values = {
            "worker_id": body.worker_id,
            "runtime_generation": generation,
            "protocol_versions": sorted(set(body.protocol_versions)),
            "task_types": sorted(set(body.task_types)),
            "last_seen_at": now,
        }
        heartbeat = case(
            (worker.c.runtime_generation != generation, None), else_=worker.c.last_heartbeat_at
        )
        if self.session.get_bind().dialect.name in {"mysql", "mariadb"}:
            statement = mysql_insert(worker).values(**values)
            # MySQL assignments run in order: compare the original generation first.
            await self.session.execute(
                statement.on_duplicate_key_update(
                    [
                        ("last_heartbeat_at", heartbeat),
                        ("runtime_generation", generation),
                        ("protocol_versions", values["protocol_versions"]),
                        ("task_types", values["task_types"]),
                        ("last_seen_at", now),
                    ]
                )
            )
        else:
            statement_sqlite = sqlite_insert(worker).values(**values)
            await self.session.execute(
                statement_sqlite.on_conflict_do_update(
                    index_elements=[worker.c.worker_id],
                    set_={
                        **{k: v for k, v in values.items() if k != "worker_id"},
                        "last_heartbeat_at": heartbeat,
                    },
                )
            )

    async def heartbeat(self, identity, now):
        await self.session.execute(
            update(IntegrationWorkerPresence)
            .where(
                IntegrationWorkerPresence.worker_id == identity.worker_id,
                IntegrationWorkerPresence.runtime_generation == identity.runtime_generation,
            )
            .values(last_seen_at=now, last_heartbeat_at=now)
        )

    async def availability(self, job, generation, now, ttl):
        worker = IntegrationWorkerPresence
        recent = [
            worker.runtime_generation == generation,
            worker.last_seen_at >= now - timedelta(seconds=ttl),
        ]
        version: ColumnElement[bool]
        task: ColumnElement[bool]
        if self.session.get_bind().dialect.name in {"mysql", "mariadb"}:
            version = func.json_contains(worker.protocol_versions, json.dumps(job.protocol_version))
            task = func.json_contains(worker.task_types, json.dumps(job.task_type))
        else:
            versions = func.json_each(worker.protocol_versions).table_valued("value")
            tasks = func.json_each(worker.task_types).table_valued("value")
            version = exists(
                select(1).select_from(versions).where(versions.c.value == job.protocol_version)
            )
            task = exists(select(1).select_from(tasks).where(tasks.c.value == job.task_type))
        if await self.session.scalar(select(exists().where(*recent, version, task))):
            return "waiting"
        online = await self.session.scalar(select(exists().where(*recent)))
        return "worker_incompatible" if online else "worker_offline"

    async def presence_summary(self, generation, now, ttl, limit):
        scope = [IntegrationWorkerPresence.runtime_generation == generation]
        online = await self.session.scalar(
            select(func.count())
            .select_from(IntegrationWorkerPresence)
            .where(*scope, IntegrationWorkerPresence.last_seen_at >= now - timedelta(seconds=ttl))
        )
        heartbeat = await self.session.scalar(
            select(func.max(IntegrationWorkerPresence.last_heartbeat_at)).where(*scope)
        )
        rows = (
            await self.session.scalars(
                select(IntegrationWorkerPresence)
                .where(*scope)
                .order_by(IntegrationWorkerPresence.last_seen_at.desc())
                .limit(limit + 1)
                .execution_options(populate_existing=True)
            )
        ).all()
        return online, heartbeat, rows

    async def prune(self, now, limit):
        cutoff = now - timedelta(days=7)
        identifiers = (
            await self.session.scalars(
                select(IntegrationWorkerPresence.worker_id)
                .where(IntegrationWorkerPresence.last_seen_at < cutoff)
                .order_by(IntegrationWorkerPresence.last_seen_at)
                .limit(limit)
            )
        ).all()
        removed = 0
        for identifier in identifiers:
            row = await self.session.scalar(
                select(IntegrationWorkerPresence)
                .where(IntegrationWorkerPresence.worker_id == identifier)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
            if row is not None and utc(row.last_seen_at) < cutoff:
                await self.session.delete(row)
                removed += 1
        await self.session.flush()
        return removed

    async def aggregate(self, now, hours, project_id, limit):
        cutoff = now - timedelta(hours=hours)
        scope = [IntegrationJob.project_id == project_id] if project_id else []
        live = (
            await self.session.execute(
                select(IntegrationJob.status, func.count())
                .where(
                    *scope,
                    IntegrationJob.status.in_(
                        ["queued", "claimed", "running", "unknown", "quarantined"]
                    ),
                )
                .group_by(IntegrationJob.status)
            )
        ).all()
        recent = (
            await self.session.execute(
                select(IntegrationJob.status, func.count())
                .where(
                    *scope,
                    IntegrationJob.created_at >= cutoff,
                )
                .group_by(IntegrationJob.status)
            )
        ).all()
        oldest = await self.session.scalar(
            select(func.min(IntegrationJob.created_at)).where(
                *scope,
                IntegrationJob.status == "queued",
            )
        )
        queue = (
            await self.session.execute(
                select(
                    func.count(IntegrationJob.queue_wait_ms),
                    func.avg(IntegrationJob.queue_wait_ms),
                    func.max(IntegrationJob.queue_wait_ms),
                ).where(*scope, IntegrationJob.first_claimed_at >= cutoff)
            )
        ).one()
        leases = (
            await self.session.execute(
                select(
                    func.count(),
                    func.sum(case((IntegrationJob.lease_expires_at <= now, 1), else_=0)),
                    func.max(IntegrationJob.heartbeat_at),
                ).where(*scope, IntegrationJob.status.in_(["claimed", "running"]))
            )
        ).one()
        measured = IntegrationJobStep.remote_recorded_at >= cutoff
        expressions = [
            func.count(case((measured, IntegrationJobStep.remote_duration_ms))),
            func.avg(case((measured, IntegrationJobStep.remote_duration_ms))),
            func.max(case((measured, IntegrationJobStep.remote_duration_ms))),
        ]
        flags = [
            IntegrationJobStep.failed_at,
            IntegrationJobStep.unknown_at,
            IntegrationJobStep.lease_lost_at,
            IntegrationJobStep.access_revoked_at,
        ]
        counts = [func.sum(case((column >= cutoff, 1), else_=0)) for column in flags]
        query = select(IntegrationJob.service_id, IntegrationJobStep.kind, *expressions, *counts)
        query = query.join(
            IntegrationJobStep, IntegrationJobStep.job_id == IntegrationJob.job_id
        ).where(
            *scope,
            IntegrationJobStep.updated_at >= cutoff,
            or_(measured, *(column >= cutoff for column in flags)),
        )
        groups = (
            await self.session.execute(
                query.group_by(IntegrationJob.service_id, IntegrationJobStep.kind)
                .order_by(IntegrationJob.service_id, IntegrationJobStep.kind)
                .limit(limit + 1)
            )
        ).all()
        totals = (
            await self.session.execute(
                select(*counts)
                .select_from(IntegrationJob)
                .join(IntegrationJobStep, IntegrationJobStep.job_id == IntegrationJob.job_id)
                .where(*scope, IntegrationJobStep.updated_at >= cutoff)
            )
        ).one()
        return {
            "live": {status: count for status, count in live},
            "recent": {status: count for status, count in recent},
            "oldest": oldest,
            "queue": queue,
            "leases": leases,
            "groups": groups,
            "totals": totals,
        }
