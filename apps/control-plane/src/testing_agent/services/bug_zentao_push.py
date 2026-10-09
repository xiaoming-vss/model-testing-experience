"""Read Bug integration context and recover verified remote associations locally."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select, update

from testing_agent.core.errors import AppError
from testing_agent.core.sid import new_id
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint
from testing_agent.schemas.bug_zentao_push import BugZentaoPushResponse
from testing_agent.services.bug_zentao_fields import BugZentaoFieldsService, update_status
from testing_agent.services.bug_zentao_options import build_options, user_options
from testing_agent.services.integration_transaction import local_transaction
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.service_instance import instance_key
from testing_agent.services.shared_service import SharedServiceService
from testing_agent.services.zentao_mcp_identity import validate_identity
from testing_agent.services.zentao_mcp_instance import discover_instance
from testing_agent.services.zentao_mcp_selection import binding_service_id, select_mcp_service

SEVERITY = {"fatal": 1, "serious": 2, "normal": 3, "minor": 4}
# 平台四档与禅道 1/2/3/4 一一对应（2026-10-09 对齐，历史 1/3/4 口径作废）。
PRIORITY = {"urgent": 1, "high": 2, "medium": 3, "low": 4}
STALE_AFTER = timedelta(minutes=5)


def remote_id(value):
    try:
        result = int(value)
        if isinstance(value, (bool, float)) or not 0 < result <= 2_147_483_647:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise AppError(400, "禅道资源编号不合法", 400) from None


def is_deleted(value):
    return str(value).lower() in ("1", "true")


class BugZentaoPushService:
    def __init__(self, bugs, connections, *, client_factory=None):
        self.bugs = bugs
        self.session = bugs.repository.session
        self.catalog = SharedServiceService(connections)
        self.client_factory = client_factory or McpClient

    async def row(self, bug_id):
        return await self.session.scalar(
            select(BugZentaoPush)
            .where(BugZentaoPush.bug_id == bug_id)
            .execution_options(populate_existing=True)
        )

    def response(self, row, **fields):
        if row:
            status = row.status
            field_status, field_error = update_status(row)
            if status == "creating" and (
                row.updated_at.replace(tzinfo=UTC) < datetime.now(UTC) - STALE_AFTER
            ):
                status = "unknown"
            fields = {
                "status": status,
                "source": row.source,
                "mcp_service_id": row.service_id,
                "remote_bug_id": row.remote_bug_id,
                "target": row.target_json,
                "error_message": row.error_message,
                "actor_user_id": row.actor_user_id,
                "updated_at": row.updated_at,
                "opened_build": row.payload_json.get("openedBuild", ["trunk"]),
                "assigned_to": row.payload_json.get("assignedTo", ""),
                "field_update_status": field_status,
                "field_update_error": field_error,
                **fields,
            }
        return BugZentaoPushResponse(**fields).model_dump(by_alias=True)

    async def local_context(self, bug, user_id, *, lock=False):
        """Resolve bindings and personal authorization without contacting MCP.

        Async submissions freeze this local target; the independent executor must
        verify the actual remote instance and resources before requesting a write permit.
        """

        def current(query):
            return (
                query.with_for_update().execution_options(populate_existing=True) if lock else query
            )

        sprint = await self.session.scalar(
            current(
                select(Sprint).where(
                    Sprint.sprint_id == bug.found_sprint_id, Sprint.project_id == bug.project_id
                )
            )
        )
        requirement = await self.session.scalar(
            current(select(Requirement).where(Requirement.requirement_id == bug.requirement_id))
        )
        if sprint is None or requirement is None:
            raise AppError(400, "推送需要有效的发现迭代和所属需求", 400)
        requirement_sprint = await self.session.scalar(
            current(
                select(Sprint).where(
                    Sprint.sprint_id == requirement.sprint_id, Sprint.project_id == bug.project_id
                )
            )
        )
        if requirement_sprint is None:
            raise AppError(400, "所属需求不属于当前项目", 400)
        bindings = []
        for kind, identifier in (
            ("project", bug.project_id),
            ("sprint", bug.found_sprint_id),
            ("requirement", bug.requirement_id),
        ):
            values = list(
                await self.session.scalars(
                    current(
                        select(ResourceBinding).where(
                            ResourceBinding.provider == "zentao",
                            ResourceBinding.status == "active",
                            ResourceBinding.local_resource_type == kind,
                            ResourceBinding.local_resource_id == identifier,
                        )
                    )
                )
            )
            if len(values) != 1:
                raise AppError(400, "项目、发现迭代和需求必须具有唯一有效的禅道绑定", 400)
            bindings.append(values[0])
        project, execution, story = bindings
        if (
            [b.remote_resource_type for b in bindings] != ["project", "execution", "story"]
            or len({b.instance_key for b in bindings}) != 1
            or any(instance_key(b.instance_url) != project.instance_key for b in bindings)
            or remote_id(execution.remote_parent_id) != remote_id(project.remote_resource_id)
            or remote_id(story.remote_parent_id) != remote_id(execution.remote_resource_id)
        ):
            raise AppError(400, "禅道绑定的实例或层级不一致，需求须属于目标执行", 400)
        chosen = binding_service_id(project)
        service = await select_mcp_service(
            self.session, bug.project_id, chosen, project.instance_url
        )
        if (
            service.zentao_instance_url
            and instance_key(service.zentao_instance_url) != project.instance_key
        ):
            raise AppError(409, "禅道 MCP 实例与当前项目绑定不一致，请先核对", 409)
        if lock:
            await self.session.refresh(service, with_for_update=True)
        own = await self.catalog.own_connection(service, user_id)
        if own is not None and lock:
            await self.session.refresh(own, with_for_update=True)
        if own is None or own.status != "active" or not (own.secret_json or {}).get("token"):
            raise AppError(400, "请先在基础服务保存本人的禅道 MCP Token", 400)
        target = {
            "mcpServiceId": service.service_id,
            "mcpName": service.name,
            "instanceUrl": project.instance_url,
            "project": remote_id(project.remote_resource_id),
            "execution": remote_id(execution.remote_resource_id),
            "story": remote_id(story.remote_resource_id),
            "projectName": project.remote_name_snapshot,
            "executionName": execution.remote_name_snapshot,
            "storyName": story.remote_name_snapshot,
        }
        return service, own, target

    async def context(self, bug, user_id):
        service, own, target = await self.local_context(bug, user_id)
        info = await discover_instance(
            service.base_url,
            self.catalog.connections._decrypt_secret(own.secret_json["token"]),
            client_factory=self.client_factory,
        )
        await validate_identity(self.session, service, info)
        if instance_key(info["instanceUrl"]) != instance_key(target["instanceUrl"]):
            raise AppError(400, "MCP 实际连接的禅道实例与资源绑定不一致", 400)
        return (
            SimpleNamespace(
                service_id=service.service_id,
                base_url=service.base_url,
                zentao_instance_url=info["instanceUrl"],
            ),
            own,
            {**target, "instanceUrl": info["instanceUrl"]},
        )

    @local_transaction
    async def set_state(
        self, bug_id, operation_id, status, *, activity_actor=None, recovered=False, **fields
    ):
        if recovered:
            from testing_agent.services.integration_recovery import lock_recovery

            await lock_recovery(self.session, bug_id, activity_actor)
        result = await self.session.execute(
            update(BugZentaoPush)
            .where(
                BugZentaoPush.bug_id == bug_id,
                BugZentaoPush.operation_id == operation_id,
            )
            .values(status=status, updated_at=datetime.now(UTC), **fields)
        )
        if result.rowcount != 1:
            await self.session.rollback()
            raise AppError(409, "推送操作已变更，请刷新后核对", 409)
        if status in ("succeeded", "failed", "unknown"):
            row = await self.row(bug_id)
            label = {"succeeded": "推送成功", "failed": "推送失败", "unknown": "结果待核对"}[status]
            detail = f"禅道 Bug #{fields['remote_bug_id']}" if fields.get("remote_bug_id") else ""
            self.session.add(
                BugActivity(
                    activity_id=new_id(),
                    bug_id=bug_id,
                    kind="sync",
                    actor_user_id=activity_actor or row.actor_user_id,
                    action="zentao_push",
                    content=f"{label} {detail}".strip(),
                    detail_json={"operationId": operation_id, "status": status},
                )
            )
        if recovered:
            from testing_agent.schemas.integration_job import IntegrationRemoteResult
            from testing_agent.services.integration_recovery import record_verified_recovery

            await record_verified_recovery(
                self.session,
                bug_id,
                operation_id,
                "create_bug",
                IntegrationRemoteResult(remote_bug_id=fields.get("remote_bug_id")),
                actor=activity_actor,
            )
        await self.session.commit()

    async def verify_target(self, client, target):
        execution = (
            await client.call("get_executions_executionID", {"executionID": target["execution"]})
        ).get("execution", {})
        story = (await client.call("get_stories_storyID", {"storyID": target["story"]})).get(
            "story", {}
        )
        if (
            remote_id(execution.get("id")) != target["execution"]
            or remote_id(execution.get("project")) != target["project"]
            or remote_id(story.get("id")) != target["story"]
            or is_deleted(execution.get("deleted"))
            or is_deleted(story.get("deleted"))
        ):
            raise AppError(400, "禅道执行或需求已变更，请重新核对绑定", 400)
        stories = (
            await client.call(
                "get_executions_executionID_stories", {"executionID": target["execution"]}
            )
        ).get("stories", [])
        if isinstance(stories, dict):
            stories = list(stories.values())
        if not isinstance(stories, list) or not any(
            isinstance(item, dict)
            and str(item.get("id")) == str(target["story"])
            and not is_deleted(item.get("deleted"))
            for item in stories
        ):
            raise AppError(400, "绑定的禅道需求不属于目标执行", 400)
        return remote_id(story.get("product"))

    async def options(self, user_id, bug_id):
        bug = await self.bugs.get_accessible_entity(user_id, bug_id, action="write")
        existing = await self.row(bug_id)
        if existing and existing.status == "succeeded":
            return await BugZentaoFieldsService(self).options(user_id, bug_id)
        if existing and existing.status not in {"failed", "preparing"}:
            raise AppError(409, "已关联或结果待核对的 Bug 不能重新选择推送字段", 409)
        service, own, target = await self.context(bug, user_id)
        token = self.catalog.connections._decrypt_secret(own.secret_json["token"])
        try:
            async with self.client_factory(service.base_url, token) as client:
                product_id = await self.verify_target(client, target)
                return {
                    "target": target,
                    "builds": await build_options(client, target, product_id),
                    "users": await user_options(client),
                }
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc

    async def reconcile(self, user_id, bug_id, remote_bug_id):
        bug = await self.bugs.get_accessible_entity(user_id, bug_id, action="write")
        row = await self.row(bug_id)
        if row is None or self.response(row)["status"] != "unknown":
            raise AppError(409, "仅结果待核对的推送可以关联已有禅道 Bug", 409)
        service, own, _ = await self.local_context(bug, user_id)
        if service.zentao_instance_url != row.instance_url:
            raise AppError(409, "禅道实例已变更，不能核对原推送", 409)
        token = self.catalog.connections._decrypt_secret(own.secret_json["token"])
        endpoint, expected_instance = service.base_url, row.instance_url
        operation, title, target = (
            row.operation_id,
            row.payload_json["title"],
            dict(row.target_json),
        )
        product = row.payload_json.get("productID")
        await self.session.commit()
        try:
            async with self.client_factory(endpoint, token) as client:
                from testing_agent.services.zentao_mcp_instance import parse_instance_info

                info = parse_instance_info(await client.call("get_zentao_instance", {}))
                if instance_key(info["instanceUrl"]) != instance_key(expected_instance):
                    raise AppError(409, "MCP 禅道实例已变化，不能核对原推送", 409)
                await validate_identity(self.session, service, info)
                await self.session.commit()
                remote = (await client.call("get_bugs_bugID", {"bugID": remote_bug_id})).get(
                    "bug", {}
                )
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc
        if (
            is_deleted(remote.get("deleted"))
            or remote_id(remote.get("id")) != remote_bug_id
            or remote.get("title") != title
            or (product is not None and remote_id(remote.get("product")) != product)
            or any(remote_id(remote.get(k)) != target[k] for k in ("project", "execution", "story"))
        ):
            raise AppError(400, "禅道 Bug 的标题或关联与本次推送不匹配", 400)
        await self.set_state(
            bug_id,
            operation,
            "succeeded",
            activity_actor=user_id,
            recovered=True,
            remote_bug_id=remote_bug_id,
            error_message="",
        )
        return self.response(await self.row(bug_id))
