"""Read attachment mappings and recover uploads using verified remote content."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from testing_agent.core.errors import AppError
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.integration_transaction import local_transaction
from testing_agent.services.mcp_client import McpCallError
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_mcp_identity import validate_identity
from testing_agent.services.zentao_mcp_instance import discover_instance
from testing_agent.services.zentao_mcp_selection import select_mcp_service

UPLOAD_TIMEOUT = 180
STALE_AFTER = timedelta(minutes=6)


class BugZentaoAttachmentService:
    def __init__(self, pushes):
        self.pushes = pushes
        self.session = pushes.session

    async def files(self, bug):
        rows = await self.session.scalars(
            select(StoredFile)
            .where(
                StoredFile.project_id == bug.project_id,
                StoredFile.resource_type == "bug",
                StoredFile.resource_id == bug.bug_id,
                StoredFile.purpose == "attachment",
                StoredFile.status == "attached",
            )
            .order_by(StoredFile.id)
        )
        return list(rows)

    async def records(self, bug_id):
        rows = await self.session.scalars(
            select(BugZentaoAttachment)
            .where(BugZentaoAttachment.bug_id == bug_id)
            .execution_options(populate_existing=True)
        )
        return {row.file_id: row for row in rows}

    async def summary(self, bug, push):
        files = await self.files(bug)
        if not files:
            return {"attachment_status": "none"}
        records = await self.records(bug.bug_id)
        statuses = []
        for file in files:
            row = records.get(file.file_id)
            status = row.status if row else "pending"
            if row and (
                row.sha256 != file.sha256
                or row.remote_bug_id != push.remote_bug_id
                or instance_key(row.instance_url) != instance_key(push.instance_url)
                or (
                    status == "uploading"
                    and row.updated_at.replace(tzinfo=UTC) < datetime.now(UTC) - STALE_AFTER
                )
            ):
                status = "unknown"
            if (
                row
                and status == "pending"
                and (row.updated_at.replace(tzinfo=UTC) >= datetime.now(UTC) - STALE_AFTER)
            ):
                status = "uploading"
            statuses.append(status)
        for status in ("unknown", "uploading", "failed", "pending"):
            if status in statuses:
                messages = {
                    "unknown": "Bug 已创建，附件结果待核对，请在禅道确认后再恢复关联",
                    "uploading": "Bug 已创建，附件正在同步，请稍后刷新",
                    "failed": "Bug 已创建，附件同步失败，可再次推送补传未成功的附件",
                    "pending": "Bug 已创建，尚有附件未同步，可再次推送补传",
                }
                message = messages[status]
                if status == "failed":
                    file_ids = {file.file_id for file in files}
                    detail = next(
                        (
                            row.error_message
                            for row in records.values()
                            if row.status == "failed" and row.file_id in file_ids
                        ),
                        "",
                    )
                    if detail:
                        message += "；" + detail
                return {
                    "attachment_status": "syncing" if status == "uploading" else status,
                    "error_message": message,
                }
        return {"attachment_status": "succeeded"}

    async def connection(self, bug, push, user_id):
        service = await select_mcp_service(
            self.session, bug.project_id, push.service_id, push.instance_url
        )
        own = await self.pushes.catalog.own_connection(service, user_id)
        if own is None or own.status != "active" or not (own.secret_json or {}).get("token"):
            raise AppError(400, "请先配置本人的禅道 MCP Token", 400)
        token = self.pushes.catalog.connections._decrypt_secret(own.secret_json["token"])
        endpoint, expected_instance = service.base_url, push.instance_url
        await self.session.commit()
        info = await discover_instance(endpoint, token, client_factory=self.pushes.client_factory)
        await validate_identity(self.session, service, info)
        if instance_key(info["instanceUrl"]) != instance_key(expected_instance):
            raise AppError(409, "禅道实例与原 Bug 推送不一致，不能上传附件", 409)
        await self.session.commit()
        return endpoint, token

    @local_transaction
    async def state(self, bug_id, file_id, operation_id, status, *, recovery_actor=None, **fields):
        if recovery_actor is not None:
            from testing_agent.services.integration_recovery import lock_recovery

            await lock_recovery(self.session, bug_id, recovery_actor)
        result = await self.session.execute(
            update(BugZentaoAttachment)
            .where(
                BugZentaoAttachment.bug_id == bug_id,
                BugZentaoAttachment.file_id == file_id,
                BugZentaoAttachment.operation_id == operation_id,
            )
            .values(status=status, updated_at=datetime.now(UTC), **fields)
        )
        if result.rowcount != 1:
            await self.session.rollback()
            raise AppError(409, "附件同步操作已变更，请刷新核对", 409)
        if recovery_actor is not None:
            from testing_agent.schemas.integration_job import IntegrationRemoteResult
            from testing_agent.services.integration_recovery import record_verified_recovery

            await record_verified_recovery(
                self.session,
                bug_id,
                operation_id,
                "upload_attachment",
                IntegrationRemoteResult(remote_file_id=fields.get("remote_file_id")),
                actor=recovery_actor,
            )
        await self.session.commit()

    async def reconcile(self, user_id, bug_id, file_id, remote_file_id):
        bug = await self.pushes.bugs.get_accessible_entity(user_id, bug_id, action="write")
        push = await self.pushes.row(bug_id)
        record = (await self.records(bug_id)).get(file_id)
        if (
            push is None
            or push.status != "succeeded"
            or record is None
            or not (
                record.status == "unknown"
                or (
                    record.status == "uploading"
                    and record.updated_at.replace(tzinfo=UTC) < datetime.now(UTC) - STALE_AFTER
                )
            )
        ):
            raise AppError(409, "仅待核对的附件可以恢复关联", 409)
        if instance_key(record.instance_url) != instance_key(push.instance_url):
            raise AppError(409, "附件的原目标已变化，不能恢复关联", 409)
        file = await self.pushes.bugs.files.accessible(user_id, file_id)
        if file.resource_type != "bug" or file.resource_id != bug_id:
            raise AppError(400, "文件不属于当前 Bug", 400)
        endpoint, token = await self.connection(bug, push, user_id)
        try:
            async with self.pushes.client_factory(endpoint, token) as client:
                data = await client.call(
                    "get_bug_attachment",
                    {
                        "bugId": push.remote_bug_id,
                        "fileId": remote_file_id,
                    },
                    timeout=UPLOAD_TIMEOUT,
                )
        except McpCallError as exc:
            raise AppError(502, "无法核对禅道附件，请检查本人权限与 MCP", 502) from exc
        if (
            data.get("status") != "success"
            or data.get("id") != remote_file_id
            or data.get("filename") != file.filename
            or data.get("size") != file.size
            or data.get("sha256") != file.sha256
            or record.sha256 != file.sha256
        ):
            raise AppError(400, "禅道附件名称或内容与本次上传不匹配", 400)
        await self.state(
            bug_id,
            file_id,
            record.operation_id,
            "succeeded",
            recovery_actor=user_id,
            remote_file_id=remote_file_id,
            error_message="",
        )
        return self.pushes.response(await self.pushes.row(bug_id), **await self.summary(bug, push))
