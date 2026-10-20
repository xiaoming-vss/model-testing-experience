"""Read remote field choices and recover verified field update results locally."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from testing_agent.core.errors import AppError
from testing_agent.core.sid import new_id
from testing_agent.domain.zentao_fields import FIELD_UPDATE_KEY as KEY
from testing_agent.domain.zentao_fields import fields_equal as equal
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.services.bug_zentao_attachment import BugZentaoAttachmentService
from testing_agent.services.bug_zentao_options import build_options, user_options
from testing_agent.services.integration_transaction import local_transaction
from testing_agent.services.mcp_client import McpCallError

STALE_AFTER = timedelta(minutes=5)


def update_status(row):
    state = (row.payload_json or {}).get(KEY, {})
    status = state.get("status", "none")
    if status in {"preparing", "updating"}:
        if row.updated_at.replace(tzinfo=UTC) < datetime.now(UTC) - STALE_AFTER:
            status = "unknown" if status == "updating" else "failed"
    error = state.get("error", "")
    if status == "unknown" and not error:
        error = "禅道版本和指派人修改结果待核对，请重新加载核对"
    return status, error


def fields(remote):
    builds = remote.get("openedBuild")
    if isinstance(builds, str):
        builds = builds.split(",")
    assignee = remote.get("assignedTo")
    if "assignedTo" in remote and assignee is None:
        assignee = ""
    if isinstance(assignee, dict):
        assignee = assignee.get("account")
    if (
        not isinstance(builds, list)
        or not builds
        or any(not isinstance(item, (str, int)) or isinstance(item, bool) for item in builds)
        or not isinstance(assignee, str)
    ):
        raise AppError(502, "禅道影响版本或指派人格式异常，无法安全修改", 502)
    return {
        "openedBuild": list(dict.fromkeys(str(item) for item in builds)),
        "assignedTo": assignee,
    }


class BugZentaoFieldsService:
    def __init__(self, pushes):
        self.pushes = pushes
        self.session = pushes.session

    async def connection(self, user_id, bug_id):
        bug = await self.pushes.bugs.get_accessible_entity(user_id, bug_id, action="write")
        row = await self.pushes.row(bug_id)
        if row is None or row.status != "succeeded" or not row.remote_bug_id:
            raise AppError(409, "只有已关联的禅道 Bug 可以修改影响版本和指派人", 409)
        endpoint, token = await BugZentaoAttachmentService(self.pushes).connection(
            bug, row, user_id
        )
        return bug, row, endpoint, token

    async def read(self, client, row):
        remote = (await client.call("get_bugs_bugID", {"bugID": row.remote_bug_id})).get("bug", {})
        if (
            str(remote.get("id")) != str(row.remote_bug_id)
            or str(remote.get("deleted", "0")).lower() in {"1", "true"}
            or any(
                str(remote.get(key)) != str(row.target_json[key])
                for key in ("project", "execution", "story")
            )
            or str(remote.get("product")) != str(row.payload_json.get("productID"))
        ):
            raise AppError(409, "原禅道 Bug 不存在或关联已变更，请先核对", 409)
        return fields(remote)

    @local_transaction
    async def finish(
        self, bug_id, operation, status, *, error="", actual=None, recovery_actor=None
    ):
        if recovery_actor is not None:
            from testing_agent.services.integration_recovery import lock_recovery

            await lock_recovery(self.session, bug_id, recovery_actor)
        row = await self.pushes.row(bug_id)
        state = (row.payload_json or {}).get(KEY, {}) if row else {}
        if state.get("operationId") != operation:
            raise AppError(409, "禅道字段修改操作已变更，请刷新核对", 409)
        if status == "succeeded" and state.get("status") == "succeeded":
            return
        payload = {**row.payload_json, KEY: {**state, "status": status, "error": error}}
        if actual is not None:
            payload.update(actual)
        result = await self.session.execute(
            update(BugZentaoPush)
            .where(
                BugZentaoPush.bug_id == bug_id,
                BugZentaoPush.payload_json[KEY]["operationId"].as_string() == operation,
                BugZentaoPush.payload_json[KEY]["status"].as_string() == state["status"],
                BugZentaoPush.status == "succeeded",
            )
            .values(payload_json=payload, updated_at=datetime.now(UTC))
        )
        if result.rowcount != 1:
            await self.session.rollback()
            raise AppError(409, "原禅道 Bug 关联已变更，请刷新核对", 409)
        if status == "succeeded" and state.get("status") != "succeeded":
            self.session.add(
                BugActivity(
                    activity_id=new_id(),
                    bug_id=bug_id,
                    kind="sync",
                    actor_user_id=state["actorUserId"],
                    action="zentao_fields_update",
                    content=f"已更新禅道 Bug #{row.remote_bug_id} 的影响版本和指派人",
                    detail_json={
                        "operationId": operation,
                        "remoteBugId": row.remote_bug_id,
                        "before": state["before"],
                        "after": actual,
                    },
                )
            )
        if recovery_actor is not None:
            from testing_agent.schemas.integration_job import IntegrationRemoteResult
            from testing_agent.services.integration_recovery import record_verified_recovery

            await record_verified_recovery(
                self.session,
                bug_id,
                operation,
                "update_fields",
                IntegrationRemoteResult.model_validate(actual),
                actor=recovery_actor,
            )
        await self.session.commit()

    async def recover(self, row, actual, user_id):
        from testing_agent.services.integration_recovery import lock_recovery

        await lock_recovery(self.session, row.bug_id, user_id)
        status, _ = update_status(row)
        if status in {"preparing", "updating"}:
            raise AppError(409, "禅道字段正在修改，请稍后重新加载", 409)
        if status == "unknown":
            state = row.payload_json[KEY]
            if not equal(actual, state["desired"]):
                raise AppError(409, "上次修改结果尚待核对，请在禅道确认后重新加载，未重复写入", 409)
            await self.finish(
                row.bug_id, state["operationId"], "succeeded", actual=actual, recovery_actor=user_id
            )
        elif status == "succeeded":
            state = row.payload_json[KEY]
            desired = state.get("desired")
            if isinstance(desired, dict) and set(desired) == set(actual) and equal(actual, desired):
                from testing_agent.schemas.integration_job import IntegrationRemoteResult
                from testing_agent.services.integration_recovery import record_verified_recovery

                await record_verified_recovery(
                    self.session,
                    row.bug_id,
                    state["operationId"],
                    "update_fields",
                    IntegrationRemoteResult.model_validate(actual),
                    actor=user_id,
                )

    async def options(self, user_id, bug_id):
        _, row, endpoint, token = await self.connection(user_id, bug_id)
        try:
            async with self.pushes.client_factory(endpoint, token) as client:
                actual = await self.read(client, row)
                await self.recover(row, actual, user_id)
                await self.session.commit()
                builds = await build_options(client, row.target_json, row.payload_json["productID"])
                users = await user_options(client)
                # Preserve remote legacy/deleted values when editing the other field.
                for identifier in actual["openedBuild"]:
                    if not any(b["id"] == identifier for b in builds):
                        builds.append({"id": identifier, "name": f"版本 #{identifier}（当前值）"})
                if actual["assignedTo"] and not any(
                    u["account"] == actual["assignedTo"] for u in users
                ):
                    users.append({"account": actual["assignedTo"], "name": "当前禅道指派人"})
                return {
                    "target": row.target_json,
                    "builds": builds,
                    "users": users,
                    "current": {"remoteBugId": row.remote_bug_id, **actual},
                }
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc
