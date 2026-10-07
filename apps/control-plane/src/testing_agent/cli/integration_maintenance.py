"""Inspect restored integration tasks or compact eligible terminal execution history."""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.config import load_settings
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_job import IntegrationJob, IntegrationJobStep
from testing_agent.services.integration_maintenance import IntegrationHistoryMaintenance
from testing_agent.services.integration_runtime import restored_runtime


async def run(args):
    settings = load_settings(args.config)
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            if args.command == "observe":
                from testing_agent.services.integration_observation import IntegrationObservation

                return await IntegrationObservation(session, settings).snapshot(
                    project_id=args.project_id, hours=args.window_hours, limit=args.limit
                )
            if args.command in {"restore-audit", "restore-isolate", "restore-release"}:
                from testing_agent.api.deps import build_integration_bug_service
                from testing_agent.schemas.integration_restore import IntegrationRestoreAudit
                from testing_agent.services.integration_restore import IntegrationRestoreService

                bugs = build_integration_bug_service(session, settings)
                review = IntegrationRestoreService(
                    session, bugs.pushes, bugs.authorization, settings
                )
                if args.command == "restore-audit":
                    files = json.loads(args.file_map.read_text()) if args.file_map else {}
                    return await review.audit(
                        IntegrationRestoreAudit(
                            restore_id=args.restore_id,
                            bug_id=args.bug_id,
                            actor_user_id=args.actor_user_id,
                            remote_bug_id=args.remote_bug_id,
                            files=files,
                        )
                    )
                if args.command == "restore-isolate":
                    return await review.isolate(
                        args.restore_id, bug_id=args.bug_id, job_id=args.job_id
                    )
                return await review.release(args.restore_id)
            if args.command == "compact":
                result = await IntegrationHistoryMaintenance(
                    session, settings.integration_execution
                ).compact()
                await session.commit()
                return result
            runtime = await restored_runtime(session)
            jobs = (
                await session.scalars(
                    select(IntegrationJob)
                    .where(
                        IntegrationJob.recovery_required.is_(True),
                        IntegrationJob.id > args.after_id,
                    )
                    .order_by(IntegrationJob.id)
                    .limit(args.limit)
                )
            ).all()
            identifiers = [job.job_id for job in jobs]
            steps = (
                (
                    await session.scalars(
                        select(IntegrationJobStep)
                        .where(IntegrationJobStep.job_id.in_(identifiers))
                        .order_by(IntegrationJobStep.id)
                    )
                ).all()
                if identifiers
                else []
            )
            return {
                "blocked": bool(runtime and runtime.blocked),
                "restoreId": runtime.restore_id if runtime else None,
                "mappingBugIds": list(
                    (
                        await session.scalars(
                            select(BugZentaoPush.bug_id)
                            .union(select(BugZentaoAttachment.bug_id))
                            .order_by("bug_id")
                            .offset(args.mapping_offset)
                            .limit(args.limit)
                        )
                    ).all()
                ),
                "nextMappingOffset": args.mapping_offset + args.limit,
                "nextAfterId": jobs[-1].id if jobs else args.after_id,
                "jobs": [
                    {
                        "jobId": job.job_id,
                        "projectId": job.project_id,
                        "bugId": job.bug_id,
                        "status": job.status,
                        "originalRuntimeGeneration": job.runtime_generation,
                        "steps": [
                            {
                                "stepKey": step.step_key,
                                "status": step.status,
                                "operationId": step.operation_id,
                            }
                            for step in steps
                            if step.job_id == job.job_id
                        ],
                    }
                    for job in jobs
                ],
            }
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "restore-review",
            "restore-audit",
            "restore-isolate",
            "restore-release",
            "compact",
            "observe",
        ],
    )
    parser.add_argument("--config", help="Generated control-plane configuration")
    parser.add_argument("--after-id", type=int, default=0)
    parser.add_argument("--limit", type=int, choices=range(1, 1001), default=100, metavar="1..1000")
    parser.add_argument("--mapping-offset", type=int, default=0)
    parser.add_argument("--project-id")
    parser.add_argument(
        "--window-hours", type=int, choices=range(1, 721), default=24, metavar="1..720"
    )
    parser.add_argument("--restore-id")
    parser.add_argument("--bug-id")
    parser.add_argument("--job-id")
    parser.add_argument("--actor-user-id")
    parser.add_argument("--remote-bug-id", type=int)
    parser.add_argument(
        "--file-map", type=Path, help="JSON mapping of local file IDs to remote IDs"
    )
    parser.add_argument(
        "--maintenance",
        action="store_true",
        help="Confirm source/target writers and in-flight external calls are stopped",
    )
    args = parser.parse_args()
    if args.command in {"restore-audit", "restore-isolate", "restore-release"}:
        if not args.maintenance or not args.restore_id:
            parser.error("Restore decisions require --maintenance and --restore-id")
        if args.command == "restore-audit" and not all(
            (args.bug_id, args.actor_user_id, args.remote_bug_id)
        ):
            parser.error("restore-audit requires --bug-id, --actor-user-id and --remote-bug-id")
        if args.command == "restore-isolate" and bool(args.bug_id) == bool(args.job_id):
            parser.error("restore-isolate requires exactly one of --bug-id and --job-id")
    if args.after_id < 0 or args.mapping_offset < 0:
        parser.error("Pagination cursors cannot be negative")
    try:
        result = asyncio.run(run(args))
    except Exception as exc:
        parser.exit(1, f"Integration maintenance failed ({type(exc).__name__}); no fence removed\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
