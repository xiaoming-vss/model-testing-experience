"""已关联 Bug 从禅道拉取更新：远端读取、基线三方比对、确认应用（R28–R34）。

全程只读禅道（R34）；应用是本地事务，按字段组以基线判断远端变化、本地
领先或双端冲突，冲突由用户逐组选择（Q02）。沿原关联实例访问（R09）。
"""

import json
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import AppError
from testing_agent.core.sid import new_id
from testing_agent.domain import zentao_bug_mapping as mapping
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.bug_zentao_sync_baseline import BugZentaoSyncBaseline
from testing_agent.repositories.zentao_bug_import import assignable_member, duplicate_local_id
from testing_agent.schemas.bug_zentao_pull import (
    ZentaoPullGroupRequest,
    ZentaoPullRequest,
    ZentaoRemoteGroupPreview,
)
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_mcp import ZentaoMcpAccess


def digest_of(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class BugZentaoPullService:
    def __init__(self, bugs, connections, *, client_factory=None):
        self.bugs = bugs
        self.repository = bugs.repository
        self.session = bugs.repository.session
        self.connections = connections
        self.client_factory = client_factory

    # ------------------------------------------------------------------ access

    async def _context(self, user_id: str, bug_id: str):
        """写权限 + 已关联校验 + 原实例访问材料（R09/R15/R17）。"""
        bug = await self.bugs.get_accessible_entity(user_id, bug_id, action="write")
        push = await self.session.scalar(
            select(BugZentaoPush)
            .where(BugZentaoPush.bug_id == bug.bug_id)
            .execution_options(populate_existing=True)
        )
        if push is None or push.status != "succeeded" or not push.remote_bug_id:
            raise AppError(409, "Bug 尚未关联禅道，请先推送或导入", 409)
        access = await ZentaoMcpAccess(self.connections).resolve(
            user_id, bug.project_id, expected_instance=push.instance_url
        )
        return bug, push, access

    async def _remote(
        self, access, remote_bug_id: int, expected_project_id: int
    ) -> tuple[dict, dict]:
        try:
            factory = self.client_factory or McpClient
            async with factory(access.endpoint, access.token) as client:
                data = await client.call("get_bugs_bugID", {"bugID": remote_bug_id})
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc
        detail = data.get("bug", {})
        if not isinstance(detail, dict):
            raise AppError(502, "禅道 Bug 详情格式异常", 502)
        try:
            snapshot = mapping.remote_snapshot(detail)
        except ValueError as exc:
            raise AppError(502, str(exc), 502) from exc
        if snapshot["deleted"]:
            raise AppError(400, "禅道 Bug 已删除或不可访问，本地数据保持不变（R14）", 400)
        if expected_project_id and int(snapshot["project"]) != expected_project_id:
            raise AppError(
                400, "禅道 Bug 已移动到其他项目，本地数据保持不变，请先核对绑定（R14/A13）", 400
            )
        return detail, snapshot

    async def _bound_project_id(self, project_id: str) -> int:
        from testing_agent.models.resource_binding import ResourceBinding

        binding = await self.session.scalar(
            select(ResourceBinding).where(
                ResourceBinding.provider == "zentao",
                ResourceBinding.status == "active",
                ResourceBinding.local_resource_type == "project",
                ResourceBinding.local_resource_id == project_id,
            )
        )
        return int(binding.remote_resource_id) if binding else 0

    @staticmethod
    def _remote_payload(snapshot: dict, description: dict) -> dict:
        return {**snapshot, "stepsDigest": description["digest"]}

    # ----------------------------------------------------------------- preview

    async def preview(self, user_id: str, bug_id: str) -> dict:
        bug, push, access = await self._context(user_id, bug_id)
        detail, snapshot = await self._remote(
            access, int(push.remote_bug_id), await self._bound_project_id(bug.project_id)
        )
        description = mapping.remote_description(detail.get("steps"))
        remote_digest = digest_of(self._remote_payload(snapshot, description))
        baselines = {
            row.field_group: row
            for row in await self.session.scalars(
                select(BugZentaoSyncBaseline).where(BugZentaoSyncBaseline.bug_id == bug.bug_id)
            )
        }
        remote_status, status_mappable = self._remote_status(snapshot)
        remote_profile, profile_mappable = self._remote_profile(snapshot)
        description_remote = {
            "digest": description["digest"],
            "hasImages": description["hasImages"],
            "hasContent": description["hasContent"],
        }
        groups = [
            self._group(
                "profile",
                self._local_profile(bug),
                remote_profile,
                baselines.get("profile"),
                mappable=profile_mappable,
            ),
            self._group(
                "description",
                {"digest": self._local_digest(bug.description_html)},
                description_remote,
                baselines.get("description"),
            ),
            self._group(
                "status",
                self._local_status(bug),
                remote_status,
                baselines.get("status"),
                mappable=status_mappable,
            ),
        ]
        account = str(snapshot["assignedTo"] or "")
        groups.append(
            ZentaoRemoteGroupPreview.model_validate(
                {
                    "group": "assignee",
                    "state": "manual",
                    "local": {"userId": bug.assignee_user_id},
                    "remote": {"account": account},
                    "baseline": self._baseline_payload(baselines.get("assignee")),
                    "reason": (
                        "禅道责任人为账号体系，需要人工映射为平台成员后应用（Q05）"
                        if account
                        else "禅道未设置责任人"
                    ),
                }
            )
        )
        return {
            "remoteBugId": int(push.remote_bug_id),
            "remoteDigest": remote_digest,
            "linkedSource": push.source,
            "groups": [group.model_dump(by_alias=True, mode="json") for group in groups],
        }

    # ------------------------------------------------------------------- apply

    async def apply(self, user_id: str, bug_id: str, body: ZentaoPullRequest) -> dict:
        bug, push, access = await self._context(user_id, bug_id)
        await self.session.refresh(bug, with_for_update=True)
        detail, snapshot = await self._remote(
            access, int(push.remote_bug_id), await self._bound_project_id(bug.project_id)
        )
        description = mapping.remote_description(detail.get("steps"))
        remote_digest = digest_of(self._remote_payload(snapshot, description))
        if remote_digest != body.remote_digest:
            raise AppError(409, "远端内容已变化，请重新预览后再应用（A09）", 409)
        operation_id = new_id()
        applied: list[str] = []
        kept: list[str] = []
        notes: list[str] = []
        changes: list[dict] = []
        for group in body.groups:
            if group.action == "keep_local":
                kept.append(group.group)
                continue
            before = self._group_values(bug, group.group)
            note = await self._apply_group(bug, push, snapshot, description, group, notes)
            if note:
                notes.append(note)
            applied.append(group.group)
            after = self._group_values(bug, group.group)
            if before != after:
                changes.append({"group": group.group, "from": before, "to": after})
        for group in body.groups:
            await self._save_baseline(bug, snapshot, description, group, operation_id)
        self.session.add(
            BugActivity(
                activity_id=new_id(),
                bug_id=bug.bug_id,
                kind="sync",
                actor_user_id=user_id,
                action="zentao_pull",
                content=(
                    f"从禅道同步：应用 {len(applied)} 组，保留 {len(kept)} 组"
                    + (f"；{len(notes)} 项待处理" if notes else "")
                ),
                detail_json={
                    "operationId": operation_id,
                    "remoteBugId": int(push.remote_bug_id),
                    "applied": applied,
                    "kept": kept,
                    "notes": notes,
                    "changes": changes,
                },
            )
        )
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            # 并发拉取撞 uk_bug_zentao_baseline：本地结果不确定，要求重新预览（R56）。
            await self.repository.rollback()
            raise AppError(409, "该 Bug 正在被其他同步操作修改，请重新预览后再应用", 409) from exc
        return {"applied": applied, "kept": kept, "notes": notes}

    def _group_values(self, bug, group: str) -> dict:
        if group == "profile":
            return self._local_profile(bug)
        if group == "description":
            return {"digest": self._local_digest(bug.description_html)}
        if group == "status":
            return self._local_status(bug)
        return {"userId": bug.assignee_user_id}

    async def _apply_group(
        self,
        bug,
        push,
        snapshot: dict,
        description: dict,
        group: ZentaoPullGroupRequest,
        notes: list[str],
    ) -> str:
        if group.group == "profile":
            severity = group.severity or mapping.map_severity(snapshot["severity"])
            priority = group.priority or mapping.map_priority(snapshot["priority"])
            if severity is None or priority is None:
                raise AppError(400, "禅道等级无法映射，请在该字段组指定平台值（Q04）", 400)
            bug.title = snapshot["title"]
            bug.severity = severity
            bug.priority = priority
        elif group.group == "description":
            if description["hasImages"]:
                raise AppError(
                    400, "远端正文包含图片，需等待文件管线反向导入后一起应用（R30）", 400
                )
            if not description["hasContent"]:
                raise AppError(400, "远端描述没有有效内容，不能清空本地描述", 400)
            bug.description_html = description["sanitized"]
        elif group.group == "status":
            status_fields = mapping.map_status(
                snapshot["status"],
                snapshot["confirmed"],
                snapshot["resolution"],
                snapshot["resolvedBuild"],
            )
            if status_fields is None:
                raise AppError(400, "禅道状态或解决方案无法映射，请保留平台值（R24）", 400)
            bug.status = status_fields["status"]
            bug.confirmed = bool(status_fields["confirmed"])
            bug.resolution = status_fields["resolution"]
            bug.resolved_build = str(status_fields["resolvedBuild"] or "")
            bug.activated_count = int(snapshot["activatedCount"])
            if status_fields["resolution"] == "duplicate" and int(snapshot["duplicateBug"]):
                duplicate = await self._duplicate_local(
                    bug.project_id, push.instance_url, int(snapshot["duplicateBug"])
                )
                if duplicate is None:
                    notes.append("远端重复 Bug 无法解析为同项目平台 Bug，本地重复关联保持不变")
                else:
                    bug.duplicate_bug = duplicate
            elif status_fields["resolution"] != "duplicate":
                bug.duplicate_bug = 0
        elif group.group == "assignee":
            if not group.assignee_user_id:
                raise AppError(400, "应用责任人需要指定平台成员（Q05）", 400)
            if not await self._assignable(bug.project_id, group.assignee_user_id):
                raise AppError(400, "责任人必须是当前项目可指派的成员", 400)
            bug.assignee_user_id = group.assignee_user_id
        return ""

    async def _save_baseline(
        self,
        bug,
        snapshot: dict,
        description: dict,
        group: ZentaoPullGroupRequest,
        operation_id: str,
    ) -> None:
        """应用或保留后写入本轮基线：本地=应用后的本地值，远端=本轮远端值（R32）。"""
        if group.group == "profile":
            local = self._local_profile(bug)
            remote = self._remote_profile(snapshot)[0]
        elif group.group == "description":
            local = {"digest": self._local_digest(bug.description_html)}
            remote = {"digest": description["digest"]}
        elif group.group == "status":
            local = self._local_status(bug)
            remote = self._remote_status(snapshot)[0]
        else:
            local = {"userId": bug.assignee_user_id}
            remote = {"account": str(snapshot["assignedTo"] or "")}
        now = datetime.now(UTC)
        row = await self.session.scalar(
            select(BugZentaoSyncBaseline).where(
                BugZentaoSyncBaseline.bug_id == bug.bug_id,
                BugZentaoSyncBaseline.field_group == group.group,
            )
        )
        if row is None:
            row = BugZentaoSyncBaseline(
                bug_id=bug.bug_id,
                field_group=group.group,
                local_snapshot_json={},
                remote_snapshot_json={},
                operation_id=operation_id,
                applied_at=now,
            )
            self.session.add(row)
        row.local_snapshot_json = local
        row.remote_snapshot_json = remote
        row.operation_id = operation_id
        row.applied_at = now

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _local_profile(bug) -> dict:
        return {"title": bug.title, "severity": bug.severity, "priority": bug.priority}

    @staticmethod
    def _remote_profile(snapshot: dict) -> tuple[dict, bool]:
        severity = mapping.map_severity(snapshot["severity"])
        priority = mapping.map_priority(snapshot["priority"])
        return (
            {
                "title": snapshot["title"],
                "severity": severity,
                "priority": priority,
            },
            severity is not None and priority is not None,
        )

    @staticmethod
    def _local_status(bug) -> dict:
        return {
            "status": bug.status,
            "confirmed": bool(bug.confirmed),
            "resolution": bug.resolution,
            "resolvedBuild": bug.resolved_build,
            "activatedCount": bug.activated_count,
        }

    @staticmethod
    def _remote_status(snapshot: dict) -> tuple[dict, bool]:
        status_fields = mapping.map_status(
            snapshot["status"],
            snapshot["confirmed"],
            snapshot["resolution"],
            snapshot["resolvedBuild"],
        )
        if status_fields is None:
            return (
                {
                    "status": str(snapshot["status"] or ""),
                    "confirmed": bool(snapshot["confirmed"]),
                    "resolution": str(snapshot["resolution"] or ""),
                    "resolvedBuild": "",
                    "activatedCount": int(snapshot["activatedCount"]),
                },
                False,
            )
        return (
            {
                "status": status_fields["status"],
                "confirmed": bool(status_fields["confirmed"]),
                "resolution": status_fields["resolution"],
                "resolvedBuild": status_fields["resolvedBuild"],
                "activatedCount": int(snapshot["activatedCount"]),
            },
            True,
        )

    @staticmethod
    def _local_digest(description_html: str) -> str:
        return sha256((description_html or "").encode()).hexdigest()

    @staticmethod
    def _baseline_payload(row: BugZentaoSyncBaseline | None) -> dict | None:
        if row is None:
            return None
        return {
            "local": row.local_snapshot_json,
            "remote": row.remote_snapshot_json,
            "appliedAt": row.applied_at,
        }

    @staticmethod
    def _group(
        group: str,
        local: dict,
        remote: dict,
        baseline: BugZentaoSyncBaseline | None,
        *,
        mappable: bool = True,
    ) -> ZentaoRemoteGroupPreview:
        state, reason = _compare(group, local, remote, baseline, mappable)
        return ZentaoRemoteGroupPreview.model_validate(
            {
                "group": group,
                "state": state,
                "local": local,
                "remote": remote,
                "baseline": BugZentaoPullService._baseline_payload(baseline),
                "reason": reason,
            }
        )

    async def _duplicate_local(self, project_id: str, instance_url: str, remote_bug_id: int):
        return await duplicate_local_id(
            self.repository, project_id, instance_key(instance_url), remote_bug_id
        )

    async def _assignable(self, project_id: str, user_id: str) -> bool:
        return await assignable_member(self.repository, project_id, user_id)


def _compare(
    group: str,
    local: dict,
    remote: dict,
    baseline: BugZentaoSyncBaseline | None,
    mappable: bool = True,
) -> tuple[str, str]:
    """基线三方比对（Q02）；返回状态与待处理原因。"""
    if group == "description" and remote.get("hasImages"):
        return "pending_files", "远端正文包含图片，需等待文件管线反向导入后一起应用（R30）"
    if not mappable:
        return "pending_map", "禅道取值无法映射到平台字段，请保留平台值或人工指定（Q04/R24）"
    current_remote = {
        key: value for key, value in remote.items() if key not in ("hasImages", "hasContent")
    }
    if baseline is None:
        if current_remote == local:
            return "synced", ""
        return "confirm_baseline", "尚无同步基线：请确认以哪一侧为准建立基线（R35）"
    baseline_remote = {
        key: value
        for key, value in baseline.remote_snapshot_json.items()
        if key not in ("hasImages", "hasContent")
    }
    baseline_local = baseline.local_snapshot_json
    local_changed = local != baseline_local
    remote_changed = current_remote != baseline_remote
    if not remote_changed:
        if local_changed:
            return "local_changed", "本地已有修改且尚未推送到禅道"
        return "synced", ""
    if not local_changed:
        return "remote_changed", ""
    return (
        ("synced", "")
        if current_remote == local
        else ("conflict", "两端都已修改且内容不同，请选择保留哪一侧")
    )
