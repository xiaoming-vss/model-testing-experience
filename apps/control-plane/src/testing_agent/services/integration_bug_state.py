"""Apply local execution state and terminal activity; recovery is an explicit capability."""

from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.sid import new_id
from testing_agent.domain.integration_execution import StepStatus, require
from testing_agent.domain.zentao_fields import FIELD_UPDATE_KEY as KEY
from testing_agent.domain.zentao_fields import fields_equal as equal
from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.integration_job import IntegrationJob, IntegrationJobStep
from testing_agent.repositories.integration_bug_state import IntegrationBugStateRepository
from testing_agent.schemas.integration_job import IntegrationRemoteResult
from testing_agent.services.bug_zentao_description import (
    source_hash,
)
from testing_agent.services.service_instance import instance_key


class RecoveryRecorder(Protocol):
    async def __call__(
        self,
        session: AsyncSession,
        bug_id: str,
        operation_id: str,
        kind: str,
        result: IntegrationRemoteResult,
        *,
        actor: str | None = None,
    ) -> None: ...


async def reject_recovery(
    session: AsyncSession,
    bug_id: str,
    operation_id: str,
    kind: str,
    result: IntegrationRemoteResult,
    *,
    actor: str | None = None,
) -> None:
    raise RuntimeError("Lifecycle projection cannot create a verified recovery receipt")


ERRORS = {
    "remote_rejected": "禅道明确拒绝本次操作",
    "remote_unavailable": "禅道连接或前置校验失败",
    "remote_uncertain": "远端写入结果待核对，请勿重复执行",
    "baseline_changed": "禅道内容已被修改，请重新加载后再同步",
    "input_changed": "本地内容或目标已变化，请重新提交",
    "access_revoked": "本人授权或项目写权限已失效",
    "dependency_failed": "依赖步骤未成功",
    "lease_lost": "执行租约已失效，写入结果待核对",
    "canceled": "任务已取消",
}


class IntegrationBugState:
    def __init__(self, session: AsyncSession, *, record_recovery: RecoveryRecorder) -> None:
        self.session = session
        self.repository = IntegrationBugStateRepository(session)
        self.record_recovery = record_recovery

    async def apply(self, job: IntegrationJob, step: IntegrationJobStep, evidence: bool) -> None:
        result = step.result_json
        row = await self.repository.push(job.bug_id)
        if row is None:
            # Deletion or explicit association reset cannot be undone by old evidence.
            if evidence:
                return
            require(step.status in {StepStatus.NOOP, StepStatus.FAILED}, "原 Bug 关联已移除")
            return
        same_target = instance_key(row.instance_url) == job.target_key
        if not same_target:
            require(evidence, "原禅道关联已切换")
            return
        if step.kind != "create_bug" and (
            row.operation_id != job.mapping_json.get("pushOperationId")
            or row.remote_bug_id != job.mapping_json.get("remoteBugId")
        ):
            require(evidence, "原 Bug 关联已变化")
            return
        if step.kind == "create_bug":
            if step.status == StepStatus.NOOP:
                require(
                    row.remote_bug_id == job.mapping_json.get("remoteBugId"), "已有 Bug 关联已变化"
                )

                await self.record_recovery(
                    self.session,
                    job.bug_id,
                    row.operation_id,
                    "create_bug",
                    IntegrationRemoteResult(remote_bug_id=row.remote_bug_id),
                    actor=job.actor_user_id,
                )
                return
            if row.operation_id != step.operation_id:
                require(evidence or step.status == StepStatus.FAILED, "原 Bug 创建操作已变化")
                return
            if step.status == StepStatus.SUCCEEDED:
                require(bool(result.get("remoteBugId")), "创建成功结果缺少远端 Bug 编号")
                row.remote_bug_id = result["remoteBugId"]
                job.mapping_json = {
                    **job.mapping_json,
                    "remoteBugId": row.remote_bug_id,
                    "productId": row.payload_json.get("productID"),
                }
            row.status = step.status
            row.error_message = ERRORS.get(result.get("errorCode", ""), "")
        elif step.kind == "upload_attachment":
            file_id = step.step_key.split(":", 1)[1]
            attachment = await self.repository.attachment(job.bug_id, file_id)
            if step.status == StepStatus.NOOP:
                if attachment is not None and attachment.status == "succeeded":
                    await self.record_recovery(
                        self.session,
                        job.bug_id,
                        attachment.operation_id,
                        "upload_attachment",
                        IntegrationRemoteResult(remote_file_id=attachment.remote_file_id),
                        actor=job.actor_user_id,
                    )
                return
            if attachment is None or attachment.operation_id != step.operation_id:
                require(evidence or step.status == StepStatus.FAILED, "原附件上传操作已变化")
                return
            if step.status == StepStatus.SUCCEEDED:
                require(bool(result.get("remoteFileId")), "上传成功结果缺少远端文件编号")
                attachment.remote_file_id = result["remoteFileId"]
                job.mapping_json = {
                    **job.mapping_json,
                    "files": {
                        **job.mapping_json.get("files", {}),
                        file_id: {
                            "remoteFileId": attachment.remote_file_id,
                            "sha256": attachment.sha256,
                        },
                    },
                }
            attachment.status = step.status
            attachment.error_message = ERRORS.get(result.get("errorCode", ""), "")
        elif step.kind == "update_fields":
            if step.status in {StepStatus.NOOP, StepStatus.FAILED} and (
                row.payload_json.get(KEY, {}).get("operationId") != step.operation_id
            ):
                return
            state = row.payload_json.get(KEY, {})
            if state.get("operationId") != step.operation_id:
                require(evidence, "原字段修改操作已变化")
                return
            fields = {k: result[k] for k in ("openedBuild", "assignedTo") if k in result}
            if step.status == StepStatus.SUCCEEDED:
                require(
                    set(fields) == {"openedBuild", "assignedTo"}
                    and equal(fields, job.snapshot_json["desired"]),
                    "字段写回读与用户指定值不一致",
                )
            row.payload_json = {
                **row.payload_json,
                **(fields if step.status == StepStatus.SUCCEEDED else {}),
                KEY: {
                    **state,
                    "status": step.status,
                    "error": ERRORS.get(result.get("errorCode", ""), ""),
                },
            }
        else:
            if step.status == StepStatus.NOOP:
                frozen = job.snapshot_json["description"]
                if not frozen["images"] and frozen["previousStatus"] == "none":
                    return
                require(
                    row.description_operation_id == frozen["previousOperationId"],
                    "原正文核对操作已变化",
                )
                row.description_status = "succeeded"
                row.description_updated_at = datetime.now(UTC)
                recovered = frozen["previousStatus"] == "unknown"
                if (
                    recovered
                    and frozen["previousOperationId"]
                    and frozen["previous"].get("desiredSteps")
                ):
                    await self.record_recovery(
                        self.session,
                        job.bug_id,
                        frozen["previousOperationId"],
                        "update_description",
                        IntegrationRemoteResult(
                            description_hash=source_hash(frozen["previous"]["desiredSteps"])
                        ),
                        actor=job.actor_user_id,
                    )
                verified_source = (
                    frozen["previous"]
                    if recovered
                    else {
                        "sourceHtml": job.snapshot_json["source"]["html"],
                        "sourceHash": frozen["sourceHash"],
                    }
                )
                row.description_sync_json = {
                    **row.description_sync_json,
                    "sourceHtml": verified_source.get("sourceHtml", ""),
                    "sourceHash": verified_source.get("sourceHash", ""),
                    "desiredSteps": frozen["previous"].get("desiredSteps", "")
                    if recovered
                    else step.input_json.get("desiredSteps", ""),
                    "errorMessage": "",
                }
                return
            if row.description_operation_id != step.operation_id:
                require(evidence or step.status == StepStatus.FAILED, "原正文同步操作已变化")
                return
            if step.status == StepStatus.SUCCEEDED:
                require(
                    result.get("descriptionHash")
                    == source_hash(row.description_sync_json["desiredSteps"]),
                    "正文写回读摘要不一致",
                )
            row.description_status = step.status
            row.description_updated_at = datetime.now(UTC)
            row.description_sync_json = {
                **row.description_sync_json,
                "errorMessage": ERRORS.get(result.get("errorCode", ""), ""),
            }

    async def sync(self, job: IntegrationJob) -> None:
        from testing_agent.models.integration_job import IntegrationJobStep

        steps = list(
            await self.session.scalars(
                select(IntegrationJobStep)
                .where(IntegrationJobStep.job_id == job.job_id)
                .order_by(IntegrationJobStep.id)
            )
        )
        for step in steps:
            if step.operation_id and step.status in {StepStatus.UNKNOWN, StepStatus.CANCELED}:
                await self.apply(job, step, True)
        if job.status in {"queued", "claimed", "running"} or job.result_json.get("activityWritten"):
            return
        bug = await self.session.scalar(select(Bug).where(Bug.bug_id == job.bug_id))
        if bug is None:
            return
        row = await self.repository.push(job.bug_id)
        if row is None:
            if job.mapping_json.get("pushOperationId"):
                return
        elif instance_key(
            row.instance_url
        ) != job.target_key or row.operation_id != job.mapping_json.get("pushOperationId"):
            return

        fields = job.task_type == "zentao_bug_fields_update"
        if fields and all(step.status == StepStatus.NOOP for step in steps):
            job.result_json = {**job.result_json, "activityWritten": True}
            return
        detail: dict[str, Any] = {
            "jobId": job.job_id,
            "status": job.status,
            "steps": job.result_json.get("steps", {}),
        }
        if fields and job.status == "succeeded":
            detail.update(before=job.snapshot_json["before"], after=job.snapshot_json["desired"])
        labels = {
            "succeeded": "已完成",
            "partial": "部分完成",
            "failed": "失败",
            "unknown": "结果待核对",
            "canceled": "已取消",
        }
        self.session.add(
            BugActivity(
                activity_id=new_id(),
                bug_id=job.bug_id,
                kind="sync",
                actor_user_id=job.actor_user_id,
                action="zentao_fields_update"
                if fields and job.status == "succeeded"
                else "zentao_sync_job",
                content=f"禅道{'字段修改' if fields else '同步'}任务{labels[job.status]}",
                detail_json=detail,
            )
        )
        job.result_json = {**job.result_json, "activityWritten": True}
