"""Bounded AI history reads. Artifact contents are loaded only by the detail path."""

from datetime import UTC

from sqlalchemy import case, func, select

from testing_agent.models.ai_generate_execution import AiGenerateRunImport as Import
from testing_agent.models.ai_generate_execution import AiGenerateRunStage as Stage
from testing_agent.models.ai_generate_execution import AiGenerateStageAttempt as Attempt
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_task import AiGenerateTaskRun as Run
from testing_agent.repositories.latest import latest_per_resource
from testing_agent.services.ai_execution import FIELDS, final_stage


def utc(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


async def history_page(session, criteria, page=1, page_size=20, pipeline_filter="all"):
    if page < 1 or not 1 <= page_size <= 100:
        from testing_agent.core.errors import ErrBadRequest

        raise ErrBadRequest()
    base_criteria = list(criteria)
    if pipeline_filter != "all":
        review = (
            select(Stage.review_status)
            .where(Stage.run_id == Run.run_id, Stage.stage == "detailed_cases")
            .scalar_subquery()
        )
        imported = select(Import.id).where(Import.run_id == Run.run_id).exists()
        pipeline = case(
            (Run.status.in_(["failed", "error"]), "failed"),
            (Run.status == "canceled", "canceled"),
            (
                Run.status.in_(["pending", "claimed", "running", "waiting_review"])
                & (func.coalesce(review, "pending") != "approved"),
                "running",
            ),
            (review == "rejected", "rejected"),
            ((review == "approved") & imported, "imported"),
            (review == "approved", "import_pending"),
            else_="review_pending",
        )
        criteria = [*criteria, pipeline == pipeline_filter]
    counts = dict(
        (
            await session.execute(
                select(Run.status, func.count())
                .join(AiGenerateTask, AiGenerateTask.task_id == Run.task_id)
                .where(*criteria)
                .group_by(Run.status)
            )
        ).all()
    )
    pending_review = (
        select(Stage.id)
        .where(
            Stage.run_id == Run.run_id,
            Stage.execution_status == "success",
            Stage.review_status == "pending",
        )
        .exists()
    )
    imported_run = select(Import.id).where(Import.run_id == Run.run_id).exists()
    review_pending_count = await session.scalar(
        select(func.count())
        .select_from(Run)
        .join(AiGenerateTask, AiGenerateTask.task_id == Run.task_id)
        .where(
            *criteria,
            (Run.status == "waiting_review")
            | ((Run.status == "success") & pending_review & ~imported_run),
        )
    )
    columns = [column for column in Run.__table__.c if column.key != "snapshot_json"]
    statement = (
        select(
            *columns,
            AiGenerateTask.project_id,
            AiGenerateTask.sprint_id,
            AiGenerateTask.requirement_id,
        )
        .select_from(Run)
        .join(AiGenerateTask, AiGenerateTask.task_id == Run.task_id)
        .where(*criteria)
        .order_by(Run.created_at.desc(), Run.id.desc())
    )
    rows = (await session.execute(statement.offset((page - 1) * page_size).limit(page_size))).all()
    # The newest run remains available for the task's start button on older pages.
    latest_statement = (
        select(
            *columns,
            AiGenerateTask.project_id,
            AiGenerateTask.sprint_id,
            AiGenerateTask.requirement_id,
        )
        .select_from(Run)
        .join(AiGenerateTask, AiGenerateTask.task_id == Run.task_id)
        .where(*base_criteria)
        .order_by(Run.created_at.desc(), Run.id.desc())
    )
    latest_rows = (
        rows[:1]
        if page == 1 and pipeline_filter == "all"
        else (await session.execute(latest_statement.limit(1))).all()
    )
    combined = {row.run_id: row for row in [*rows, *latest_rows]}
    summaries = await summarize(session, list(combined.values()))
    return {
        "items": [summaries[row.run_id] for row in rows],
        "total": sum(counts.values()),
        "statusCounts": counts,
        "reviewPendingCount": review_pending_count,
        "latestRun": summaries[latest_rows[0].run_id] if latest_rows else None,
    }


async def summarize(session, runs):
    if not runs:
        return {}
    ids = [run.run_id for run in runs]
    stages = list(
        (
            await session.scalars(
                select(Stage).where(Stage.run_id.in_(ids)).order_by(Stage.stage_order)
            )
        ).all()
    )
    attempts = (
        await session.execute(
            latest_per_resource(
                select(
                    Attempt.stage_id, Attempt.error_message, Attempt.remediation, Attempt.created_at
                )
                .join(Stage, Stage.id == Attempt.stage_id)
                .where(Stage.run_id.in_(ids)),
                Attempt.stage_id,
                Attempt.attempt_no,
                Attempt.id,
            )
        )
    ).all()
    latest = {row.stage_id: row for row in attempts}
    artifacts = (
        await session.execute(
            select(
                Attempt.id,
                Attempt.stage_id,
                (func.length(Attempt.output_content) > 0).label("has_content"),
            )
            .join(Stage, Stage.current_artifact_attempt_id == Attempt.id)
            .where(Stage.run_id.in_(ids), Stage.id == Attempt.stage_id)
        )
    ).all()
    available = {row.stage_id for row in artifacts if row.has_content}
    imports = {
        row.run_id: row
        for row in (await session.scalars(select(Import).where(Import.run_id.in_(ids)))).all()
    }
    by_run: dict[str, list[Stage]] = {run_id: [] for run_id in ids}
    for stage in stages:
        by_run[stage.run_id].append(stage)
    result = {}
    for run in runs:
        graph = by_run[run.run_id]
        if not graph:
            from testing_agent.core.errors import ErrNotFound

            raise ErrNotFound()
        final = final_stage(graph)
        current = next(
            (s for s in graph if s.stage == run.current_stage),
            final if run.current_stage == "completed" else graph[0],
        )
        attempt = latest.get(current.id)
        imported = imports.get(run.run_id)
        status = current.execution_status
        stage_status = (
            ("waiting_review" if run.status == "waiting_review" else "completed")
            if status == "success"
            else status
        )
        timestamps = [utc(run.created_at), *[utc(s.updated_at) for s in graph]]
        if imported:
            timestamps.append(utc(imported.imported_at or imported.created_at))
        if attempt:
            timestamps.append(utc(attempt.created_at))
        duration = (
            max(0, int((utc(run.finished_at) - utc(run.started_at)).total_seconds() * 1000))
            if run.started_at and run.finished_at
            else 0
        )
        result[run.run_id] = {
            "runId": run.run_id,
            "taskId": run.task_id,
            "projectId": run.project_id,
            "sprintId": run.sprint_id,
            "requirementId": run.requirement_id,
            "triggerUserId": run.trigger_user_id,
            "triggerType": "manual",
            "status": run.status,
            "workflowVersion": 2,
            "checkpointEnabled": run.checkpoint_enabled,
            "currentStage": run.current_stage,
            "stageStatus": stage_status if run.current_stage else "",
            "reviewStatus": final.review_status
            if final.review_status != "not_required"
            else "pending",
            "reviewerUserId": final.reviewer_user_id or "",
            "reviewedAt": final.reviewed_at,
            "reviewComment": final.review_comment or "",
            "importStatus": "imported" if imported else "pending",
            "importedAt": imported.imported_at if imported else None,
            "importedTargets": imported.imported_targets_json or [] if imported else [],
            "importMigrationComplete": True,
            "durationMs": duration,
            "errorMessage": attempt.error_message or "" if attempt else "",
            "remediation": attempt.remediation or "" if attempt else "",
            "createdAt": run.created_at,
            "startedAt": run.started_at,
            "finishedAt": run.finished_at,
            "updatedAt": max(t for t in timestamps if t),
            "availableArtifacts": [
                FIELDS[s.stage] for s in graph if s.id in available and s.stage in FIELDS
            ],
            "hasResult": final.id in available,
        }
    return result
