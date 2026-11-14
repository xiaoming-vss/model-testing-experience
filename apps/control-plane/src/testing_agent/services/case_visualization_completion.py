"""Validate and atomically publish visualization results in the Worker event transaction."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.case_visualization.contract import (
    STATE_IDENTITY_MESSAGE,
    canonical,
    freeze_input,
    validate_artifact,
)
from testing_agent.models.case_visualization import TestOrderEntryVisualization
from testing_agent.models.test_order_entry import TestOrderEntry
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import WorkerTaskEventRequest
from testing_agent.services.stage_storage.worker import StageWorkerTransitions
from testing_agent.services.worker_domains.events import final_run_status


async def complete_visualization(
    session: AsyncSession,
    task: WorkerTask,
    *,
    stage_id: str,
    attempt_id: str,
    source: dict[str, Any],
    frozen_config: dict[str, Any],
    body: WorkerTaskEventRequest,
) -> None:
    if (body.task_id and body.task_id != task.task_id) or (
        body.run_id and body.run_id != attempt_id
    ):
        raise ErrBadRequest()
    transitions = StageWorkerTransitions(session)
    await transitions.current(stage_id, attempt_id, task.task_id)
    status = final_run_status(body.status)
    if status not in {"success", "failed", "error", "canceled"}:
        raise ErrBadRequest()
    binding = await session.scalar(
        select(TestOrderEntryVisualization)
        .where(
            TestOrderEntryVisualization.task_id == source.get("taskId"),
            TestOrderEntryVisualization.entry_id == source.get("entryId"),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    entry = await session.scalar(
        select(TestOrderEntry)
        .where(
            TestOrderEntry.entry_id == source.get("entryId"),
            TestOrderEntry.order_id == source.get("orderId"),
        )
        .execution_options(populate_existing=True)
    )
    safe_state_error = "图解结果校验失败：状态保持时前后状态必须使用同一实体，请重新生成"
    error = (
        safe_state_error
        if body.error_message == safe_state_error
        else "图解生成失败，请重试或继续使用文字模式"
    )
    artifact = None
    if status == "success":
        try:
            if binding is None or entry is None:
                raise ValueError("执行条目已不存在")
            frozen = frozen_config["visualizationInput"]
            current = freeze_input(entry.entry_id, entry.snapshot_json)
            if current != frozen or current["snapshotHash"] != source.get("snapshotHash"):
                raise ValueError("图解输入快照已失效")
            raw = body.result_yaml or body.output_yaml or ""
            artifact = validate_artifact(frozen, raw)
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            status = "failed"
            error = (
                safe_state_error
                if type(exc) is ValueError and str(exc) == STATE_IDENTITY_MESSAGE
                else "图解结果校验失败或输入已失效，请重新生成"
            )
    if status == "success" and artifact is not None and binding is not None:
        metadata = body.result_summary_json
        context: dict[str, Any] = {"artifactStatus": artifact["status"], "schemaVersion": "1.0"}
        if isinstance(metadata, dict):
            details = metadata.get("visualization", {})
            if isinstance(details, dict):
                digest = details.get("skillDigest")
                if (
                    isinstance(digest, str)
                    and len(digest) == 64
                    and all(c in "0123456789abcdef" for c in digest)
                ):
                    context["skillDigest"] = digest
                model = details.get("model")
                if isinstance(model, str) and len(model) <= 256:
                    context["model"] = model
        await transitions.completed(
            stage_id,
            attempt_id,
            task.task_id,
            content=canonical(artifact),
            output_format="json",
            output_context=context,
        )
        if artifact["status"] in {"ready", "partial"}:
            binding.effective_attempt_id = attempt_id
            binding.effective_snapshot_hash = source["snapshotHash"]
    else:
        await transitions.failed(
            stage_id, attempt_id, task.task_id, error_message=error, status=status
        )
        task.error_message = error
    task.status = status
    task.finished_at = datetime.now(UTC)
    task.lease_expires_at = task.finished_at
