"""Build and revalidate credential-free Bug execution snapshots using only local state."""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.domain.integration_execution import digest, utc
from testing_agent.domain.rich_text import extract_file_ids
from testing_agent.models.bug import Bug
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_job import IntegrationJobStep
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.stored_file import StoredFile
from testing_agent.schemas.bug_zentao_push import BugZentaoPushRequest, BugZentaoUpdateRequest
from testing_agent.schemas.integration_job import IntegrationStepPlan, IntegrationSubmission
from testing_agent.services.bug_zentao_attachment import BugZentaoAttachmentService
from testing_agent.services.bug_zentao_description import source_hash
from testing_agent.services.bug_zentao_fields import equal, update_status
from testing_agent.services.bug_zentao_push import PRIORITY, SEVERITY, STALE_AFTER
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_mcp_selection import binding_service_id, select_mcp_service


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AppError(409, message, 409)


def source(bug, files: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": bug.title,
        "html": bug.description_html,
        "severity": bug.severity,
        "priority": bug.priority,
        "foundSprintId": bug.found_sprint_id,
        "requirementId": bug.requirement_id,
        "files": files,
    }


class IntegrationBugContext:
    def __init__(self, pushes, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.pushes = pushes
        self.session = pushes.session
        self.attachments = BugZentaoAttachmentService(pushes)
        self.clock = clock

    async def manifest(self, bug, *, lock=False) -> list[dict[str, Any]]:
        if lock:
            files = list(
                await self.session.scalars(
                    select(StoredFile)
                    .where(
                        StoredFile.project_id == bug.project_id,
                        StoredFile.resource_type == "bug",
                        StoredFile.resource_id == bug.bug_id,
                        StoredFile.purpose == "attachment",
                        StoredFile.status == "attached",
                    )
                    .order_by(StoredFile.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
        else:
            files = await self.attachments.files(bug)
        return [
            {
                "fileId": f.file_id,
                "filename": f.filename,
                "contentType": f.content_type,
                "size": f.size,
                "sha256": f.sha256,
            }
            for f in files
        ]

    async def bindings(self, bug, *, lock=False) -> list[dict[str, Any]]:
        bindings: list[dict[str, Any]] = []
        for kind, identifier in (
            ("project", bug.project_id),
            ("sprint", bug.found_sprint_id),
            ("requirement", bug.requirement_id),
        ):
            query = (
                select(ResourceBinding)
                .where(
                    ResourceBinding.provider == "zentao",
                    ResourceBinding.status == "active",
                    ResourceBinding.local_resource_type == kind,
                    ResourceBinding.local_resource_id == identifier,
                )
                .order_by(ResourceBinding.id)
            )
            if lock:
                query = query.with_for_update()
            rows = list(await self.session.scalars(query.execution_options(populate_existing=True)))
            bindings.extend(
                {
                    "bindingId": row.binding_id,
                    "kind": kind,
                    "localId": identifier,
                    "remoteKind": row.remote_resource_type,
                    "remoteId": row.remote_resource_id,
                    "parentId": row.remote_parent_id,
                    "instance": row.instance_key,
                    "serviceId": binding_service_id(row),
                }
                for row in rows
            )
        return bindings

    async def local_target(self, bug, actor, row, *, lock=False):
        if row is None or row.status != "succeeded" or not row.remote_bug_id:
            return await self.pushes.local_context(bug, actor, lock=lock)
        service = await select_mcp_service(
            self.session, bug.project_id, row.service_id, row.instance_url
        )
        if lock:
            await self.session.refresh(service, with_for_update=True)
        require(
            not service.zentao_instance_url
            or instance_key(service.zentao_instance_url) == instance_key(row.instance_url),
            "原禅道 Bug 的 MCP 实例记录不一致，请先核对",
        )
        own = await self.pushes.catalog.own_connection(service, actor)
        if own is not None and lock:
            await self.session.refresh(own, with_for_update=True)
        if own is None or own.status != "active" or not (own.secret_json or {}).get("token"):
            raise ErrForbidden()
        project_bindings = [
            b for b in await self.bindings(bug, lock=lock) if b["kind"] == "project"
        ]
        require(len(project_bindings) == 1, "项目禅道绑定已移除或不唯一")
        bound = project_bindings[0]
        require(
            bound["instance"] == instance_key(row.instance_url)
            and str(bound["remoteId"]) == str(row.target_json["project"])
            and (not bound["serviceId"] or bound["serviceId"] == row.service_id),
            "原禅道 Bug 的项目或 MCP 关联已变化",
        )
        target = dict(row.target_json)
        if "instanceUrl" in target:
            require(
                isinstance(target["instanceUrl"], str)
                and instance_key(target["instanceUrl"]) == instance_key(row.instance_url),
                "原禅道 Bug 的实例记录不一致，请先核对",
            )
        # Older confirmed pushes stored only project/execution/story in target_json.
        # Enrich the returned view from authoritative columns; keep history unchanged.
        target.setdefault("instanceUrl", row.instance_url)
        target.setdefault("mcpServiceId", service.service_id)
        target.setdefault("mcpName", service.name)
        return service, own, target

    async def target_revision(self, bug, actor, row) -> tuple[str, Any, Any, dict[str, Any]]:
        service, own, target = await self.local_target(bug, actor, row, lock=True)
        semantic_target = {key: target[key] for key in ("project", "execution", "story")}
        semantic_target["instance"] = instance_key(target["instanceUrl"])
        revision = digest(
            {
                "target": semantic_target,
                "bindings": await self.bindings(bug, lock=True),
                "serviceId": service.service_id,
                "endpoint": service.base_url,
            }
        )
        return revision, service, own, target

    async def entities(self, actor, bug_id):
        await self.pushes.bugs.get_accessible_entity(actor, bug_id, action="write")
        bug = await self.session.scalar(
            select(Bug)
            .where(Bug.bug_id == bug_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = await self.session.scalar(
            select(BugZentaoPush)
            .where(BugZentaoPush.bug_id == bug_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        require(bug is not None, "Bug 已删除")
        return bug, row

    async def current(self, job):
        bug, row = await self.entities(job.actor_user_id, job.bug_id)
        revision, service, own, target = await self.target_revision(bug, job.actor_user_id, row)
        require(
            service.service_id == job.service_id and own.connection_id == job.connection_id,
            "任务绑定的服务或本人连接已变化",
        )
        require(revision == job.target_revision, "集成目标已变化")
        if job.task_type == "zentao_bug_sync":
            require(
                digest(source(bug, await self.manifest(bug, lock=True))) == job.input_revision,
                "本地 Bug 正文或附件已变化",
            )
        expected = job.mapping_json.get("remoteBugId")
        if expected:
            require(
                row is not None
                and row.status == "succeeded"
                and row.remote_bug_id == expected
                and row.operation_id == job.mapping_json.get("pushOperationId"),
                "原禅道 Bug 关联已变化",
            )
        return bug, row, service, own, target

    async def retryable_attachment(self, record: BugZentaoAttachment | None) -> bool:
        if record is None or record.status == "failed":
            return True
        if record.status != "pending" or utc(record.updated_at) >= self.clock() - STALE_AFTER:
            return False
        if not record.operation_id:
            return True
        original_status = await self.session.scalar(
            select(IntegrationJobStep.status).where(
                IntegrationJobStep.operation_id == record.operation_id,
                IntegrationJobStep.kind == "upload_attachment",
            )
        )
        # The ledger overrides legacy preparation: unknown or confirmed writes
        # cannot be resent, even when an old domain row says pending.
        return original_status in {None, "failed", "blocked"}

    async def build_sync(self, actor, bug_id, request_id, request: BugZentaoPushRequest):
        bug, row = await self.entities(actor, bug_id)
        if row and row.status != "succeeded":
            stale_preflight = row.status == "preparing" and utc(row.updated_at) < (
                self.clock() - STALE_AFTER
            )
            require(
                row.status == "failed" or stale_preflight, "原 Bug 创建仍在执行或结果未知，请先核对"
            )
        revision, service, own, target = await self.target_revision(bug, actor, row)
        if request.expected_target is not None:
            require(request.expected_target == target, "禅道目标已变化，请重新加载")
        files = await self.manifest(bug, lock=True)
        original = source(bug, files)
        remote_bug_id = row.remote_bug_id if row and row.status == "succeeded" else None
        steps = [IntegrationStepPlan(step_key="create_bug", kind="create_bug")]
        records = await self.attachments.records(bug_id)
        blocked = []
        mapping: dict[str, Any] = {
            "remoteBugId": remote_bug_id,
            "pushOperationId": row.operation_id if row else "",
            "files": {},
        }
        for file in files:
            key = "upload_attachment:" + file["fileId"]
            record = records.get(file["fileId"])
            if record is not None:
                same = (
                    record.sha256 == file["sha256"]
                    and record.remote_bug_id == remote_bug_id
                    and instance_key(record.instance_url) == instance_key(target["instanceUrl"])
                )
                if same and record.status == "succeeded" and record.remote_file_id:
                    mapping["files"][file["fileId"]] = {
                        "remoteFileId": record.remote_file_id,
                        "sha256": record.sha256,
                    }
                else:
                    retryable = await self.retryable_attachment(record)
                    if not retryable or not same:
                        blocked.append(key)
            steps.append(
                IntegrationStepPlan(
                    step_key=key, kind="upload_attachment", dependencies=["create_bug"], input=file
                )
            )
        images = sorted(extract_file_ids(bug.description_html))
        require(set(images).issubset({f["fileId"] for f in files}), "正文图片附件已移除")
        previous = dict(row.description_sync_json or {}) if row else {}
        previous_status = row.description_status if row else "none"
        stale_preparation = (
            previous_status == "preparing"
            and row is not None
            and row.description_updated_at is not None
            and utc(row.description_updated_at) < self.clock() - STALE_AFTER
        )
        require(
            previous_status not in {"preparing", "syncing"} or stale_preparation,
            "原正文仍在同步，请先等待或核对",
        )
        description = {
            "sourceHtml": bug.description_html,
            "sourceHash": source_hash(bug.description_html),
            "expectedSteps": (
                previous.get("desiredSteps", "")
                if previous_status == "succeeded"
                else previous.get("expectedSteps", (row.payload_json or {}).get("steps", ""))
                if row
                else ""
            ),
            "previous": previous,
            "previousStatus": previous_status,
            "previousOperationId": row.description_operation_id if row else "",
            "images": images,
        }
        steps.append(
            IntegrationStepPlan(
                step_key="update_description",
                kind="update_description",
                dependencies=[
                    "create_bug",
                    *("upload_attachment:" + identifier for identifier in images),
                ],
                input=description,
            )
        )
        payload = {
            "title": bug.title,
            "steps": re.sub(r"<img\b[^>]*>", "", bug.description_html, flags=re.IGNORECASE),
            "openedBuild": request.opened_build,
            "severity": SEVERITY[bug.severity],
            "pri": PRIORITY[bug.priority],
            **{key: target[key] for key in ("project", "execution", "story")},
        }
        if request.assigned_to:
            payload["assignedTo"] = request.assigned_to
        snapshot = {
            "source": original,
            "target": target,
            "createPayload": payload,
            "existingPayload": dict(row.payload_json or {}) if row else {},
            "description": description,
            "blockedSteps": blocked,
            "clientRequest": digest(request.model_dump(mode="json", by_alias=True)),
        }
        return IntegrationSubmission(
            request_id=request_id,
            task_type="zentao_bug_sync",
            project_id=bug.project_id,
            bug_id=bug_id,
            actor_user_id=actor,
            service_id=service.service_id,
            connection_id=own.connection_id,
            target_key=instance_key(target["instanceUrl"]),
            input_revision=digest(original),
            target_revision=revision,
            snapshot=snapshot,
            mapping=mapping,
            steps=steps,
        )

    async def build_fields(self, actor, bug_id, request_id, request: BugZentaoUpdateRequest):
        bug, row = await self.entities(actor, bug_id)
        require(
            row is not None and row.status == "succeeded" and bool(row.remote_bug_id),
            "只有已关联的禅道 Bug 可以修改字段",
        )
        require(
            update_status(row)[0] not in {"preparing", "updating", "unknown"},
            "原字段修改未完成核对，请先重新加载",
        )
        require(
            request.expected_remote_bug_id == row.remote_bug_id
            and request.expected_target == row.target_json,
            "原禅道 Bug 关联已变化",
        )
        revision, service, own, target = await self.target_revision(bug, actor, row)
        before = {
            "openedBuild": request.expected_opened_build,
            "assignedTo": request.expected_assigned_to,
        }
        desired = {"openedBuild": request.opened_build, "assignedTo": request.assigned_to}
        snapshot = {
            "target": target,
            "before": before,
            "desired": desired,
            "existingPayload": dict(row.payload_json or {}),
            "clientRequest": digest(request.model_dump(mode="json", by_alias=True)),
            "unchanged": equal(before, desired),
        }
        return IntegrationSubmission(
            request_id=request_id,
            task_type="zentao_bug_fields_update",
            project_id=bug.project_id,
            bug_id=bug_id,
            actor_user_id=actor,
            service_id=service.service_id,
            connection_id=own.connection_id,
            target_key=instance_key(target["instanceUrl"]),
            input_revision=digest({"before": before, "desired": desired}),
            target_revision=revision,
            snapshot=snapshot,
            mapping={"remoteBugId": row.remote_bug_id, "pushOperationId": row.operation_id},
            steps=[
                IntegrationStepPlan(
                    step_key="update_fields",
                    kind="update_fields",
                    input={"before": before, "desired": desired},
                )
            ],
        )
