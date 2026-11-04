"""editable draft and review commands for direct stage storage."""

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from testing_agent.core.errors import AppError, ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.db.savepoint import ensure_outer_transaction
from testing_agent.domain.generation_chain import is_final_stage, stage_names, upstream_stages
from testing_agent.domain.request_identity import request_signature
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.schemas.generation_chain import (
    GenerationChainReviewRequest,
    GenerationChainRevisionRequest,
    GenerationChainRunRequest,
    GenerationChainSaveDraftRequest,
    GenerationChainView,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_artifact_validation import validate_generation_artifact
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.revision_attachments import (
    attach_revision_attachments,
    normalize_attachment_file_ids,
)
from testing_agent.services.stage_storage import DirectStageStorage
from testing_agent.services.stage_storage.chain_view import build_chain_view
from testing_agent.services.stage_storage.dispatch import (
    dispatch_stage_attempt,
    replay_stage_attempt,
    reserve_worker_identity,
)
from testing_agent.services.stage_storage.run_command import start_stage
from testing_agent.services.stage_storage.views import attempt_source

if TYPE_CHECKING:
    from testing_agent.services.generation_chain import GenerationChainService


class DirectStageCommands:
    def __init__(self, chain: "GenerationChainService") -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.storage = DirectStageStorage(self.session)

    async def _stage(self, task_id: str, stage: str) -> AiGenerationStage:
        row = await self.session.scalar(
            select(AiGenerationStage)
            .where(AiGenerationStage.task_id == task_id, AiGenerationStage.stage == stage)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise dynamic_error(ErrBadRequest, "当前阶段还没有可审核的产物")
        return row

    async def run(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        body: GenerationChainRunRequest,
        user_id: str,
    ) -> GenerationChainView:
        self.chain.validate_stage(kind, stage)
        task = await self.chain.task(requirement_id, kind, user_id, action="execute", lock=True)
        await start_stage(self.chain, task, kind, stage, body, user_id)
        await self.session.commit()
        return await build_chain_view(self.session, requirement_id, kind, task, detail=True)

    async def save(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        body: GenerationChainSaveDraftRequest,
        user_id: str,
    ) -> GenerationChainView:
        self.chain.validate_stage(kind, stage)
        task = await self.chain.task(requirement_id, kind, user_id, action="write", lock=True)
        row = await self._stage(task.task_id, stage)
        current = await self.session.scalar(
            select(AiGenerationAttempt).where(
                AiGenerationAttempt.id == body.expected_attempt_id,
                AiGenerationAttempt.stage_id == row.id,
            )
        )
        if current is None or row.current_attempt_id != current.id:
            raise dynamic_error(ErrBadRequest, "阶段产物已变化，请刷新后重新编辑")
        content, output_format = await validate_generation_artifact(
            self.chain.tasks, kind, stage, body.content, attempt_source(current)
        )
        await self.storage.save_draft(
            row.id,
            expected_attempt_id=current.id,
            requested_by=user_id,
            content=content,
            output_format=output_format,
        )
        await self.session.commit()
        return await build_chain_view(self.session, requirement_id, kind, task, detail=True)

    async def _revise(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        body: GenerationChainRevisionRequest,
        user_id: str,
    ) -> AiGenerateTask:
        self.chain.validate_stage(kind, stage)
        task = await self.chain.task(requirement_id, kind, user_id, action="execute", lock=True)
        if kind == "ui" and body.attachment_file_ids:
            raise dynamic_error(ErrBadRequest, "UI 阶段暂不支持附加优化图片，请移除后重试")
        worker_id = str(body.request_id) if body.request_id else str(uuid4())
        file_ids = normalize_attachment_file_ids(body.attachment_file_ids)
        signature = request_signature(
            "generation-stage-revise",
            {
                "kind": kind,
                "stage": stage,
                "connectionId": body.connection_id,
                "instruction": body.instruction,
                "attachmentFileIds": file_ids,
            },
        )
        await require_personal_connection(
            self.session, user_id, "llm", body.connection_id, task.project_id
        )
        attempt_id = str(uuid4())
        worker, replay = await reserve_worker_identity(self.session, task, worker_id, attempt_id)
        if replay:
            await replay_stage_attempt(
                self.session,
                worker=worker,
                task=task,
                stage_name=stage,
                actor_id=user_id,
                operation="revise",
                signature=signature,
            )
            return task
        row = await self._stage(task.task_id, stage)
        current = await self.session.scalar(
            select(AiGenerationAttempt).where(AiGenerationAttempt.id == row.current_attempt_id)
        )
        if current is None or current.stage_id != row.id:
            raise dynamic_error(ErrBadRequest, "当前阶段还没有可优化的产物")
        snapshot = current.input_snapshot_json or {}
        if not isinstance(snapshot, dict):
            raise ErrBadRequest()
        versioning = snapshot.get("versioning") or {}
        source = snapshot.get("source") or {}
        if not isinstance(versioning, dict) or not isinstance(source, dict):
            raise ErrBadRequest()
        upstream = versioning.get("upstreamVersions") or {}
        if not isinstance(upstream, dict):
            raise ErrBadRequest()
        ids = {value for value in upstream.values() if isinstance(value, str) and value}
        source_version = source.get("requirementUnderstandingVersion")
        if (
            isinstance(source_version, dict)
            and isinstance(source_version.get("versionId"), str)
            and source_version["versionId"]
        ):
            ids.add(source_version["versionId"])
        if ids:
            await self.chain.lock_upstream_versions(sorted(ids))
        attachments: tuple[dict[str, str], ...] = ()
        if file_ids:
            files = self.chain.files
            if files is None:
                raise dynamic_error(ErrBadRequest, "文件存储未配置，不能附加图片")
            attachments = await attach_revision_attachments(
                files,
                user_id=user_id,
                project_id=task.project_id,
                run_id=attempt_id,
                file_ids=file_ids,
            )
        await dispatch_stage_attempt(
            self.session,
            task=task,
            stage_id=row.id,
            request_id=worker_id,
            actor_id=user_id,
            input_snapshot={"llmConnectionId": body.connection_id, "requestSignature": signature},
            operation="revise",
            expected_attempt_id=current.id,
            revision_instruction=body.instruction,
            revision_attachments=attachments,
            attempt_id=attempt_id,
            reserved_worker=worker,
        )
        return task

    async def revise(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        body: GenerationChainRevisionRequest,
        user_id: str,
    ) -> GenerationChainView:
        await self.session.run_sync(ensure_outer_transaction)
        async with self.session.begin_nested():
            task = await self._revise(requirement_id, kind, stage, body, user_id)
        await self.session.commit()
        return await build_chain_view(self.session, requirement_id, kind, task, detail=True)

    async def review(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        body: GenerationChainReviewRequest,
        user_id: str,
    ) -> GenerationChainView:
        self.chain.validate_stage(kind, stage)
        task = await self.chain.task(requirement_id, kind, user_id, action="review", lock=True)
        row = await self._stage(task.task_id, stage)
        if not body.expected_attempt_id or body.expected_attempt_id != row.current_attempt_id:
            raise dynamic_error(ErrBadRequest, "阶段产物已变化，请刷新后重新审核")
        attempt = await self.session.scalar(
            select(AiGenerationAttempt).where(
                AiGenerationAttempt.id == body.expected_attempt_id,
                AiGenerationAttempt.stage_id == row.id,
            )
        )
        if attempt is None:
            raise ErrNotFound()
        version_query = select(AiGenerateStageVersion).where(
            AiGenerateStageVersion.task_id == task.task_id,
            AiGenerateStageVersion.stage == stage,
            AiGenerateStageVersion.attempt_id == attempt.id,
        )
        if row.review_status == "approved":
            version_query = version_query.with_for_update().execution_options(
                populate_existing=True
            )
        existing = await self.session.scalar(version_query)
        review_signature = request_signature(
            "generation-stage-review",
            {
                "kind": kind,
                "stage": stage,
                "action": body.action,
                "expectedAttemptId": body.expected_attempt_id,
                "continueAfter": body.continue_after,
                "comment": body.comment,
                "instruction": body.instruction,
                "connectionId": body.connection_id,
            },
        )
        if existing is not None:
            if body.action != "approve":
                raise dynamic_error(ErrBadRequest, "已审核通过的阶段不能重新驳回")
            context = existing.artifact_context_json or {}
            identity = context.get("reviewRequest") if isinstance(context, dict) else None
            if (
                body.request_id
                and isinstance(identity, dict)
                and identity.get("id") == str(body.request_id)
            ):
                if (
                    identity.get("signature") != review_signature
                    or existing.reviewer_user_id != user_id
                ):
                    raise dynamic_error(ErrBadRequest, "请求标识已用于其他审核操作")
                if body.continue_after:
                    snapshot = attempt.input_snapshot_json or {}
                    connection = body.connection_id or snapshot.get("llmConnectionId") or ""
                    await self.session.commit()
                    return await self._continue_review(
                        requirement_id, kind, stage, body, user_id, connection, existing
                    )
            return await build_chain_view(self.session, requirement_id, kind, task, detail=True)
        if body.continue_after and (body.action != "approve" or is_final_stage(kind, stage)):
            raise dynamic_error(ErrBadRequest, "当前阶段不能审核通过并继续")
        snapshot = attempt.input_snapshot_json or {}
        if not isinstance(snapshot, dict):
            raise ErrBadRequest()
        continuation_connection = body.connection_id or snapshot.get("llmConnectionId") or ""
        if body.action == "reject":
            await self.storage.reject(row.id, expected_attempt_id=attempt.id)
        elif body.action == "approve":
            await validate_generation_artifact(
                self.chain.tasks, kind, stage, attempt.output_content or "", attempt_source(attempt)
            )
            versioning = snapshot.get("versioning") or {}
            source = snapshot.get("source") or {}
            if not isinstance(versioning, dict) or not isinstance(source, dict):
                raise ErrBadRequest()
            upstream = versioning.get("upstreamVersions") or {}
            source_version = source.get("requirementUnderstandingVersion") or {}
            if not isinstance(upstream, dict):
                raise ErrBadRequest()
            ids = {value for value in upstream.values() if isinstance(value, str) and value}
            if (
                isinstance(source_version, dict)
                and isinstance(source_version.get("versionId"), str)
                and source_version["versionId"]
            ):
                ids.add(source_version["versionId"])
            if ids:
                locked = list(
                    (
                        await self.session.scalars(
                            select(AiGenerateStageVersion)
                            .where(AiGenerateStageVersion.version_id.in_(ids))
                            .order_by(AiGenerateStageVersion.id)
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                    ).all()
                )
                if {value.version_id for value in locked} != ids:
                    raise dynamic_error(ErrBadRequest, "选择的上游版本已删除，请重新选择")
            version = await self.storage.approve(
                row.id,
                expected_attempt_id=attempt.id,
                reviewer_user_id=user_id,
                comment=body.comment,
            )
            if body.request_id:
                version.artifact_context_json = {
                    **(version.artifact_context_json or {}),
                    "reviewRequest": {"id": str(body.request_id), "signature": review_signature},
                }
        else:
            raise ErrBadRequest()
        await self.session.commit()
        if body.continue_after:
            return await self._continue_review(
                requirement_id, kind, stage, body, user_id, continuation_connection, version
            )
        return await build_chain_view(self.session, requirement_id, kind, task, detail=True)

    async def _continue_review(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        body: GenerationChainReviewRequest,
        user_id: str,
        connection: object,
        version: AiGenerateStageVersion,
    ) -> GenerationChainView:
        try:
            if not isinstance(connection, str) or not connection:
                raise dynamic_error(ErrBadRequest, "请选择模型连接")
            next_stage = stage_names(kind)[stage_names(kind).index(stage) + 1]
            upstream = version.upstream_versions_json or {}
            selected = {
                key: value
                for key, value in upstream.items()
                if key in upstream_stages(kind, next_stage) and isinstance(value, str)
            }
            if stage in upstream_stages(kind, next_stage):
                selected[stage] = version.version_id
            return await self.run(
                requirement_id,
                kind,
                next_stage,
                GenerationChainRunRequest(
                    connection_id=connection,
                    instruction=body.instruction,
                    request_id=body.request_id,
                    upstream_versions=selected,
                ),
                user_id,
            )
        except AppError as exc:
            await self.session.rollback()
            refreshed = await self.chain.task(requirement_id, kind, user_id, action="read")
            view = await build_chain_view(
                self.session, requirement_id, kind, refreshed, detail=True
            )
            view.continuation_error = exc.message
            return view
