"""Safe queue explanations and operator snapshots, separate from write permits."""

from datetime import UTC, datetime

from testing_agent.domain.integration_execution import utc
from testing_agent.repositories.integration_job import IntegrationJobRepository
from testing_agent.repositories.integration_observation import IntegrationObservationRepository
from testing_agent.services.integration_runtime import isolated_scope, restored_runtime


def stamp(value):
    return utc(value).isoformat() if value is not None else None


class IntegrationObservation:
    def __init__(self, session, settings, *, clock=lambda: datetime.now(UTC)):
        self.repository = IntegrationObservationRepository(session)
        self.settings, self.clock = settings, clock

    async def contact(self, body):
        await self.repository.contact(
            body, self.settings.integration_execution.runtime_generation, self.clock()
        )

    async def heartbeat(self, identity):
        await self.repository.heartbeat(identity, self.clock())

    async def prune(self):
        return await self.repository.prune(
            self.clock(), self.settings.integration_execution.maintenance_batch_size
        )

    async def explain(self, job):
        if job.status != "queued":
            return {}
        execution = self.settings.integration_execution
        runtime = await restored_runtime(self.repository.session)
        isolated = bool(runtime and await isolated_scope(self.repository.session, job.bug_id))
        if job.runtime_generation != execution.runtime_generation:
            reason = "runtime_changed"
        elif (
            not execution.uses_worker(job.project_id)
            or not execution.claim_enabled
            or bool(runtime and runtime.blocked)
            or isolated
        ):
            reason = "paused"
        elif await IntegrationJobRepository(self.repository.session).target_busy(job.target_key):
            reason = "target_busy"
        else:
            reason = await self.repository.availability(
                job,
                execution.runtime_generation,
                self.clock(),
                execution.worker_presence_ttl_seconds,
            )
        return {
            "queueReason": reason,
            "queueWaitSeconds": max(0, int((self.clock() - utc(job.created_at)).total_seconds())),
        }

    async def snapshot(self, *, project_id=None, hours=24, limit=100):
        if not 1 <= hours <= 720 or not 1 <= limit <= 1000:
            raise ValueError("Observation window or limit is invalid")
        now = self.clock()
        data = await self.repository.aggregate(now, hours, project_id, limit)
        execution = self.settings.integration_execution
        online, last_heartbeat, workers = await self.repository.presence_summary(
            execution.runtime_generation, now, execution.worker_presence_ttl_seconds, limit
        )
        runtime = await restored_runtime(self.repository.session)
        queue, leases = data["queue"], data["leases"]
        names = (
            "failedOperations",
            "unknownOperations",
            "leaseLostOperations",
            "accessRevokedOperations",
        )
        return {
            "asOf": stamp(now),
            "projectId": project_id,
            "windowHours": hours,
            "executionEnabled": self.settings.integration_execution.enabled,
            "claimEnabled": self.settings.integration_execution.claim_enabled,
            "restoreBlocked": bool(runtime and runtime.blocked),
            "liveJobsByStatus": data["live"],
            "submittedJobsByStatus": data["recent"],
            "queue": {
                "oldestWaitSeconds": max(0, int((now - utc(data["oldest"])).total_seconds()))
                if data["oldest"]
                else None,
                "firstClaimSamples": queue[0],
                "averageWaitMs": float(queue[1]) if queue[1] is not None else None,
                "maximumWaitMs": queue[2],
            },
            "leases": {
                "active": leases[0],
                "expired": int(leases[1] or 0),
                "lastHeartbeatAt": stamp(leases[2]),
            },
            "operationCounts": {
                name: int(value or 0) for name, value in zip(names, data["totals"], strict=True)
            },
            "services": [
                {
                    "serviceId": row[0],
                    "stepKind": row[1],
                    "durationSamples": row[2],
                    "averageRemoteMs": float(row[3]) if row[3] is not None else None,
                    "maximumRemoteMs": row[4],
                    **{name: int(value or 0) for name, value in zip(names, row[5:], strict=True)},
                }
                for row in data["groups"][:limit]
            ],
            "serviceGroupsTruncated": len(data["groups"]) > limit,
            "onlineWorkers": online,
            "lastWorkerHeartbeatAt": stamp(last_heartbeat),
            "workers": [
                {
                    "workerId": row.worker_id,
                    "protocolVersions": row.protocol_versions,
                    "taskTypes": row.task_types,
                    "lastSeenAt": stamp(row.last_seen_at),
                    "lastHeartbeatAt": stamp(row.last_heartbeat_at),
                    "online": (now - utc(row.last_seen_at)).total_seconds()
                    <= execution.worker_presence_ttl_seconds,
                }
                for row in workers[:limit]
            ],
            "workersTruncated": len(workers) > limit,
            "measurementScope": (
                "Persisted first observations per operation; duration is Worker-reported; "
                "pre-0033 measurements are unavailable"
            ),
        }
