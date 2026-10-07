"""Detach project remote IDs atomically; retain Bug sync history in its activity feed."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, true, update

from testing_agent.core.errors import AppError
from testing_agent.core.sid import new_id
from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.test_order import TestOrder
from testing_agent.models.test_order_entry import TestOrderEntry
from testing_agent.services.zentao_mcp_identity import project_binding_scope, service_associations


async def clear_project_associations(session, project_id, actor, new_instance, *, resource=None):
    from testing_agent.services.integration_lifecycle import change_target

    await change_target(
        session,
        project_id=project_id,
        service_id=resource.service_id if resource is not None else "",
        include_unknown=False,
    )
    bug_ids = select(Bug.bug_id).where(Bug.project_id == project_id)
    pushes = list(
        await session.scalars(
            select(BugZentaoPush).where(BugZentaoPush.bug_id.in_(bug_ids)).with_for_update()
        )
    )
    attachments = list(
        await session.scalars(
            select(BugZentaoAttachment)
            .where(BugZentaoAttachment.bug_id.in_(bug_ids))
            .with_for_update()
        )
    )
    binding_ids = None
    source_entry_ids = []
    if resource is not None:
        owned_bindings, owned_pushes, owned_attachments = await service_associations(
            session, resource
        )
        root_owned = any(row.local_resource_type == "project" for row in owned_bindings)
        if not root_owned:
            binding_ids = [row.binding_id for row in owned_bindings]
            push_bug_ids = {row.bug_id for row in owned_pushes}
            attachment_ids = {(row.bug_id, row.file_id) for row in owned_attachments}
            pushes = [row for row in pushes if row.bug_id in push_bug_ids]
            attachments = [
                row for row in attachments if (row.bug_id, row.file_id) in attachment_ids
            ]
            source_entry_ids = list(
                await session.scalars(
                    select(Bug.source_entry_id).where(
                        Bug.project_id == project_id, Bug.bug_id.in_(push_bug_ids)
                    )
                )
            )
    now = datetime.now(UTC)
    if any(
        (row.payload_json or {}).get("_fieldUpdate", {}).get("status") in {"preparing", "updating"}
        and row.updated_at.replace(tzinfo=UTC) >= now - timedelta(minutes=5)
        for row in pushes
    ):
        raise AppError(409, "有禅道 Bug 字段正在修改，请完成后再切换禅道", 409)
    if any(
        row.status in {"preparing", "creating"}
        and row.updated_at.replace(tzinfo=UTC) >= now - timedelta(minutes=5)
        for row in pushes
    ):
        raise AppError(409, "有 Bug 正在推送，请完成后再切换禅道", 409)
    if any(
        row.status in {"pending", "uploading"}
        and row.updated_at.replace(tzinfo=UTC) >= now - timedelta(minutes=6)
        for row in attachments
    ):
        raise AppError(409, "有 Bug 附件正在同步，请完成后再切换禅道", 409)
    if any(
        row.description_status in {"preparing", "syncing"}
        and row.description_updated_at
        and row.description_updated_at.replace(tzinfo=UTC) >= now - timedelta(minutes=6)
        for row in pushes
    ):
        raise AppError(409, "有 Bug 正文图片正在同步，请完成后再切换禅道", 409)
    histories = {}
    for row in pushes:
        histories[row.bug_id] = {
            "instanceUrl": row.instance_url,
            "remoteBugId": row.remote_bug_id,
            "status": row.status,
            "operationId": row.operation_id,
            "target": row.target_json,
            "payload": row.payload_json,
            "actorUserId": row.actor_user_id,
            "createdAt": row.created_at.isoformat(),
            "updatedAt": row.updated_at.isoformat(),
            "errorMessage": row.error_message,
            "descriptionStatus": row.description_status,
            "descriptionSync": row.description_sync_json,
        }
    for row in attachments:
        snapshot = histories.setdefault(row.bug_id, {})
        snapshot.setdefault("attachments", []).append(
            {
                "fileId": row.file_id,
                "instanceUrl": row.instance_url,
                "remoteBugId": row.remote_bug_id,
                "remoteFileId": row.remote_file_id,
                "status": row.status,
                "operationId": row.operation_id,
                "sha256": row.sha256,
                "actorUserId": row.actor_user_id,
                "errorMessage": row.error_message,
                "createdAt": row.created_at.isoformat(),
                "updatedAt": row.updated_at.isoformat(),
            }
        )
    for bug_id, history in histories.items():
        session.add(
            BugActivity(
                activity_id=new_id(),
                bug_id=bug_id,
                kind="sync",
                actor_user_id=actor,
                action="zentao_instance_reset",
                content=(
                    "切换禅道，已清除旧推送关联；原禅道数据保留"
                    + (
                        f"（原 Bug #{history['remoteBugId']}）"
                        if history.get("remoteBugId")
                        else ""
                    )
                ),
                detail_json={"newInstanceUrl": new_instance, "previousAssociation": history},
            )
        )
    await session.execute(
        delete(ResourceBinding).where(
            project_binding_scope(project_id),
            ResourceBinding.binding_id.in_(binding_ids) if binding_ids is not None else true(),
        )
    )
    order_ids = select(TestOrder.order_id).where(TestOrder.project_id == project_id)
    await session.execute(
        update(TestOrderEntry)
        .where(
            TestOrderEntry.order_id.in_(order_ids),
            TestOrderEntry.entry_id.in_(source_entry_ids) if binding_ids is not None else true(),
        )
        .values(zentao_bug_id="")
    )
    await session.execute(
        delete(BugZentaoAttachment).where(
            BugZentaoAttachment.id.in_([row.id for row in attachments])
        )
    )
    await session.execute(
        delete(BugZentaoPush).where(BugZentaoPush.bug_id.in_([row.bug_id for row in pushes]))
    )
