"""direct stage persistence.

The caller holds the outer transaction and owns authorization, validation,
worker queue creation, input freezing and upstream version locks.
"""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.domain.generation_chain import STAGE_CONFIG_FIELDS, artifact_value
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.ui_generation_sources import ui_source_inputs


class DirectStageStorage:
    """Read and modify one stable stage using the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_stage(self, stage_id: str) -> AiGenerationStage:
        stage = await self.session.scalar(
            select(AiGenerationStage)
            .where(AiGenerationStage.id == stage_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if stage is None:
            raise ErrNotFound()
        return stage

    async def current(self, stage: AiGenerationStage) -> AiGenerationAttempt | None:
        if not stage.current_attempt_id:
            return None
        return await self.session.scalar(
            select(AiGenerationAttempt)
            .where(
                AiGenerationAttempt.id == stage.current_attempt_id,
                AiGenerationAttempt.stage_id == stage.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def _versioned(self, attempt_id: str) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count())
                .select_from(AiGenerateStageVersion)
                .where(AiGenerateStageVersion.attempt_id == attempt_id)
            )
        )

    async def _next_attempt_no(self, stage_id: str) -> int:
        maximum = await self.session.scalar(
            select(func.max(AiGenerationAttempt.attempt_no)).where(
                AiGenerationAttempt.stage_id == stage_id
            )
        )
        return (maximum or 0) + 1

    async def prepare(
        self,
        stage_id: str,
        *,
        worker_task_id: str,
        requested_by: str,
        input_snapshot: dict[str, Any],
        operation: str = "generate",
        expected_attempt_id: str | None = None,
        revision_instruction: str | None = None,
        revision_attachments: tuple[dict[str, str], ...] = (),
        attempt_id: str | None = None,
        execution_id: str | None = None,
        new_execution_id: str | None = None,
        review_required: bool = True,
    ) -> AiGenerationAttempt:
        """Reserve a generation attempt; caller enqueues its worker in this transaction."""
        stage = await self.lock_stage(stage_id)
        current = await self.current(stage)
        if stage.active_attempt_id:
            raise dynamic_error(ErrBadRequest, "阶段正在运行")
        current_is_versioned = await self._versioned(current.id) if current else False
        draft_exists = bool(
            review_required
            and stage.review_status == "pending"
            and current is not None
            and current.status == "success"
            and current.output_content
            and current.invalidated_at is None
            and not current_is_versioned
        )
        if (
            not worker_task_id
            or not requested_by
            or operation not in {"generate", "retry", "revise"}
        ):
            raise ErrBadRequest()
        snapshot = deepcopy(input_snapshot)
        if operation == "revise":
            if (
                not draft_exists
                or current is None
                or current.id != expected_attempt_id
                or not revision_instruction
                or not revision_instruction.strip()
            ):
                raise ErrBadRequest()
            snapshot = deepcopy(current.input_snapshot_json or {})
            config = deepcopy(snapshot.get("config") or {})
            source = deepcopy(snapshot.get("source") or {})
            if not isinstance(config, dict) or not isinstance(source, dict):
                raise ErrBadRequest()
            config.update(
                {
                    k: deepcopy(v)
                    for k, v in (current.output_context_json or {}).items()
                    if k != "moduleGeneration"
                }
            )
            config.pop("revisionAttachments", None)
            config.pop("revisionInstruction", None)
            field = STAGE_CONFIG_FIELDS.get(stage.stage)
            if field:
                config[field] = artifact_value(
                    stage.stage, current.output_content or "", current.output_format
                )
            if revision_attachments:
                config["revisionAttachments"] = [dict(item) for item in revision_attachments]
            snapshot["config"] = config
            snapshot["source"] = {**source, "instruction": revision_instruction}
            snapshot["currentOutput"] = current.output_content or ""
            snapshot["llmConnectionId"] = input_snapshot.get("llmConnectionId")
            if "requestSignature" in input_snapshot:
                snapshot["requestSignature"] = input_snapshot["requestSignature"]
            else:
                snapshot.pop("requestSignature", None)
        elif draft_exists:
            raise dynamic_error(ErrBadRequest, "阶段已有待审核内容")
        if execution_id and new_execution_id:
            raise ErrBadRequest()
        if execution_id:
            execution = await self.session.scalar(
                select(AiExecution)
                .where(
                    AiExecution.execution_id == execution_id,
                    AiExecution.task_id == stage.task_id,
                )
                .with_for_update()
            )
            if execution is None or execution.workflow_status is not None:
                raise ErrBadRequest()
        else:
            execution = AiExecution(
                execution_id=new_execution_id or str(uuid4()),
                task_id=stage.task_id,
                requested_by=requested_by,
            )
            self.session.add(execution)
        attempt = AiGenerationAttempt(
            id=attempt_id or str(uuid4()),
            stage_id=stage.id,
            execution_id=execution.execution_id,
            attempt_no=await self._next_attempt_no(stage.id),
            operation=operation,
            worker_task_id=worker_task_id,
            requested_by=requested_by,
            input_snapshot_json=snapshot,
            revision_instruction=revision_instruction if operation == "revise" else None,
            status="pending",
            invalidated_reason="",
            created_at=datetime.now(UTC),
        )
        self.session.add(attempt)
        stage.active_attempt_id = attempt.id
        stage.review_status = "pending" if review_required else "not_required"
        await self.session.flush()
        return attempt

    async def publish(
        self,
        stage_id: str,
        *,
        attempt_id: str,
        worker_task_id: str,
        content: str,
        output_format: str,
        output_context: dict[str, Any] | None,
    ) -> AiGenerationAttempt:
        """Publish a verified worker result only for the currently active attempt."""
        stage = await self.lock_stage(stage_id)
        attempt = await self.session.scalar(
            select(AiGenerationAttempt)
            .where(AiGenerationAttempt.id == attempt_id, AiGenerationAttempt.stage_id == stage_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            attempt is None
            or stage.active_attempt_id != attempt_id
            or attempt.worker_task_id != worker_task_id
            or attempt.status not in {"pending", "claimed", "running"}
            or not content.strip()
        ):
            raise ErrBadRequest()
        attempt.output_content = content
        attempt.output_format = output_format
        attempt.output_context_json = deepcopy(output_context)
        attempt.status = "success"
        attempt.finished_at = datetime.now(UTC)
        stage.active_attempt_id = None
        stage.current_attempt_id = attempt.id
        if stage.review_status != "not_required":
            stage.review_status = "pending"
        await self.session.flush()
        return attempt

    async def save_draft(
        self,
        stage_id: str,
        *,
        expected_attempt_id: str,
        requested_by: str,
        content: str,
        output_format: str,
    ) -> AiGenerationAttempt:
        """Save an already validated whole draft, using the candidate ID as CAS token."""
        stage = await self.lock_stage(stage_id)
        current = await self.current(stage)
        if (
            stage.active_attempt_id
            or stage.review_status != "pending"
            or current is None
            or current.id != expected_attempt_id
            or await self._versioned(current.id)
            or current.status != "success"
            or current.invalidated_at is not None
            or not content.strip()
        ):
            raise ErrBadRequest()
        attempt = AiGenerationAttempt(
            id=str(uuid4()),
            stage_id=stage.id,
            attempt_no=await self._next_attempt_no(stage.id),
            operation="edit",
            requested_by=requested_by,
            input_snapshot_json=deepcopy(current.input_snapshot_json),
            output_content=content,
            output_format=output_format,
            output_context_json={
                key: deepcopy(value)
                for key, value in (current.output_context_json or {}).items()
                if key != "moduleGeneration"
            }
            if current.output_context_json is not None
            else None,
            status="success",
            invalidated_reason="",
            created_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        self.session.add(attempt)
        stage.current_attempt_id = attempt.id
        await self.session.flush()
        return attempt

    async def approve(
        self,
        stage_id: str,
        *,
        expected_attempt_id: str,
        reviewer_user_id: str,
        comment: str,
    ) -> AiGenerateStageVersion:
        """Create an immutable approved snapshot in the caller's transaction."""
        stage = await self.lock_stage(stage_id)
        current = await self.current(stage)
        if (
            stage.active_attempt_id
            or stage.review_status != "pending"
            or current is None
            or current.id != expected_attempt_id
            or await self._versioned(current.id)
            or current.status != "success"
            or current.invalidated_at is not None
            or not current.output_content
        ):
            raise ErrBadRequest()
        snapshot = current.input_snapshot_json or {}
        if not isinstance(snapshot, dict):
            raise ErrBadRequest()
        versioning = snapshot.get("versioning") or {}
        if not isinstance(versioning, dict):
            raise ErrBadRequest()
        upstream = versioning.get("upstreamVersions")
        if upstream is not None and not isinstance(upstream, dict):
            raise ErrBadRequest()
        source = snapshot.get("source") or {}
        if not isinstance(source, dict):
            raise ErrBadRequest()
        task_type = await self.session.scalar(
            select(AiGenerateTask.task_type).where(AiGenerateTask.task_id == stage.task_id)
        )
        if task_type is None:
            raise ErrNotFound()
        if (
            upstream is None
            and task_type == "functional_case_generate"
            and stage.stage == "requirement_analysis"
        ):
            source_version = source.get("requirementMaterialVersion")
            if (
                isinstance(source_version, dict)
                and isinstance(source_version.get("versionId"), str)
                and source_version["versionId"]
            ):
                upstream = {"extracting_text": source_version["versionId"]}
        context = deepcopy(current.output_context_json or {})
        context.pop("moduleGeneration", None)
        if task_type == "ui_case_generate":
            context["uiSourceBatchId"] = source.get("uiSourceBatchId") or current.id
            context["uiSourceInputs"] = ui_source_inputs(source)
        elif task_type == "functional_case_generate":
            context["functionalSource"] = {
                key: deepcopy(value)
                for key, value in source.items()
                if key in {"sourceContent", "requirementMaterialVersion", "documentType"}
            }
        elif (
            task_type == "api_case_generate"
            and source.get("apiWorkflowVersion") == "api_two_stage/1.0"
        ):
            context["apiWorkflowVersion"] = "api_two_stage/1.0"
        now = datetime.now(UTC)
        version = AiGenerateStageVersion(
            version_id=f"sv-{uuid4()}",
            task_id=stage.task_id,
            stage=stage.stage,
            version_no=stage.next_version_no,
            attempt_id=current.id,
            artifact_content=current.output_content,
            artifact_format=current.output_format or "text",
            artifact_context_json=context,
            upstream_versions_json=deepcopy(upstream),
            reviewer_user_id=reviewer_user_id,
            reviewed_at=now,
            review_comment=comment,
            created_at=now,
        )
        stage.next_version_no += 1
        stage.review_status = "approved"
        self.session.add(version)
        await self.session.flush()
        return version

    async def reject(self, stage_id: str, *, expected_attempt_id: str) -> None:
        """Clear every unapproved attempt of this stage in the caller's transaction.

        Worker errors shared with another attempt remain untouched.
        """
        stage = await self.lock_stage(stage_id)
        current = await self.current(stage)
        if (
            stage.active_attempt_id
            or stage.review_status != "pending"
            or current is None
            or current.id != expected_attempt_id
            or await self._versioned(current.id)
            or current.status != "success"
        ):
            raise ErrBadRequest()
        versioned = select(AiGenerateStageVersion.attempt_id).where(
            AiGenerateStageVersion.task_id == stage.task_id,
            AiGenerateStageVersion.stage == stage.stage,
        )
        unversioned = list(
            (
                await self.session.scalars(
                    select(AiGenerationAttempt)
                    .where(
                        AiGenerationAttempt.stage_id == stage.id,
                        AiGenerationAttempt.id.not_in(versioned),
                        AiGenerationAttempt.status.not_in(
                            {"pending", "queued", "claimed", "running"}
                        ),
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        request_signatures = {
            attempt.id: snapshot["requestSignature"]
            for attempt in unversioned
            if isinstance((snapshot := attempt.input_snapshot_json), dict)
            and isinstance(snapshot.get("requestSignature"), str)
        }
        ids = {attempt.id for attempt in unversioned}
        new_workers = {attempt.worker_task_id for attempt in unversioned if attempt.worker_task_id}
        if new_workers:
            held_workers = set(
                (
                    await self.session.scalars(
                        select(AiGenerationAttempt.worker_task_id).where(
                            AiGenerationAttempt.worker_task_id.in_(new_workers),
                            AiGenerationAttempt.id.not_in(ids),
                        )
                    )
                ).all()
            )
            safe_workers = new_workers - held_workers
            try:
                queues = (
                    list(
                        (
                            await self.session.scalars(
                                select(WorkerTask)
                                .where(
                                    WorkerTask.domain == "ai", WorkerTask.task_id.in_(safe_workers)
                                )
                                .with_for_update(nowait=True)
                                .execution_options(populate_existing=True)
                            )
                        ).all()
                    )
                    if safe_workers
                    else []
                )
            except OperationalError as exc:
                if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
                    raise dynamic_error(ErrBadRequest, "阶段仍在处理回传，请稍后重试") from exc
                raise
            for queue in queues:
                queue.error_message = ""
        await self.session.execute(
            update(AiGenerationAttempt)
            .where(
                AiGenerationAttempt.stage_id == stage.id,
                AiGenerationAttempt.id.not_in(versioned),
                AiGenerationAttempt.status.not_in({"pending", "queued", "claimed", "running"}),
            )
            .values(
                input_snapshot_json=None,
                revision_instruction=None,
                output_content=None,
                output_format=None,
                output_context_json=None,
                error_message=None,
                invalidated_reason="审核未通过，候选产物已丢弃",
                invalidated_at=datetime.now(UTC),
            )
        )
        for attempt in unversioned:
            if attempt.id in request_signatures:
                attempt.input_snapshot_json = {"requestSignature": request_signatures[attempt.id]}
        stage.current_attempt_id = None
        stage.review_status = "pending"
        await self.session.flush()
