from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from testing_agent.core.enums import BugActivityKind
from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.bug_zentao_sync_baseline import BugZentaoSyncBaseline
from testing_agent.repositories.bug import BugRepository
from testing_agent.repositories.zentao_bug_import import import_by_operation, remote_link
from testing_agent.services.bug_import.contracts import (
    BugImportResult,
    BugImportTarget,
    PreparedBugImport,
    import_result,
)
from testing_agent.services.service_instance import instance_key


def _identity_conflict(exc: IntegrityError) -> bool:
    detail = str(exc.orig)
    return "uk_bug_zentao_remote_identity" in detail or (
        "bug_zentao_pushes.instance_key" in detail and "remote_bug_id" in detail
    )


def _bug_no_conflict(exc: IntegrityError) -> bool:
    detail = str(exc.orig)
    return "uk_bugs_project_bug_no" in detail or (
        "UNIQUE constraint failed: bugs.project_id, bugs.bug_no" in detail
    )


class BugImportWriter:
    def __init__(self, repository: BugRepository, *, id_factory: Callable[[], str]) -> None:
        self.repository = repository
        self.session = repository.session
        self.new_id = id_factory

    async def replay(self, operation_id: str) -> BugImportResult | None:
        """同一请求编号的重复提交返回原结果，不重复创建（R11/R56）。"""
        row = await import_by_operation(self.session, operation_id)
        if row is None or row.source != "import":
            return None
        bug = await self.repository.get_bug(row.bug_id)
        if bug is None:
            return None
        return import_result(
            int(row.remote_bug_id or 0),
            "success",
            bug_id=bug.bug_id,
            bug_no=bug.bug_no,
            title=bug.title,
        )

    async def create(
        self, context: BugImportTarget, prepared: PreparedBugImport
    ) -> BugImportResult:
        user_id, project_id, operation_id = (
            context.user_id,
            context.project_id,
            context.operation_id,
        )
        snapshot, status_fields, description = (
            prepared.snapshot,
            prepared.status,
            prepared.description,
        )
        resolved, pending = prepared.resolved, prepared.pending
        instance_url = context.instance_url
        target = {
            "mcpServiceId": context.service_id,
            "instanceUrl": instance_url,
            "project": context.remote_project_id,
        }
        bug = Bug(
            bug_id=self.new_id(),
            bug_no=0,
            project_id=project_id,
            title=snapshot["title"],
            # 带图正文先落去图文本（R41）；完整净化文本用于无图场景。
            description_html=(
                description["textOnly"] if description["hasImages"] else description["sanitized"]
            ),
            status=status_fields["status"],
            confirmed=bool(status_fields["confirmed"]),
            resolution=status_fields["resolution"],
            resolved_build=str(status_fields.get("resolvedBuild") or ""),
            duplicate_bug=resolved["duplicate_bug"],
            activated_count=int(snapshot["activatedCount"]),
            severity=resolved["severity"],
            priority=resolved["priority"],
            reporter_user_id=user_id,
            assignee_user_id=resolved["assignee_user_id"],
            found_sprint_id=resolved["found_sprint_id"],
            planned_fix_sprint_id="",
            requirement_id=resolved["requirement_id"],
        )
        create_activity = BugActivity(
            activity_id=self.new_id(),
            bug_id=bug.bug_id,
            kind=BugActivityKind.STATUS_CHANGE.value,
            actor_user_id=user_id,
            action="create",
            from_status="",
            to_status=bug.status,
        )
        sync_activity = BugActivity(
            activity_id=self.new_id(),
            bug_id=bug.bug_id,
            kind="sync",
            actor_user_id=user_id,
            action="zentao_import",
            content=f"从禅道导入 Bug #{snapshot['remoteBugId']}",
            detail_json={
                "operationId": operation_id,
                "remoteBugId": snapshot["remoteBugId"],
                "openedBy": snapshot["openedBy"],
                "openedDate": snapshot["openedDate"],
            },
        )
        push = BugZentaoPush(
            bug_id=bug.bug_id,
            source="import",
            operation_id=operation_id,
            actor_user_id=user_id,
            service_id=context.service_id,
            instance_url=instance_url,
            instance_key=instance_key(instance_url),
            status="succeeded",
            remote_bug_id=snapshot["remoteBugId"],
            target_json=target,
            payload_json={},
        )
        remote_profile = {
            "title": snapshot["title"],
            "severity": resolved["severity"],
            "priority": resolved["priority"],
        }
        # duplicateBug 解析为平台主键后不可与远端编号直接比较，不进入比对基线。
        remote_status = {
            "status": status_fields["status"],
            "confirmed": bool(status_fields["confirmed"]),
            "resolution": status_fields["resolution"],
            "resolvedBuild": str(status_fields.get("resolvedBuild") or ""),
            "activatedCount": int(snapshot["activatedCount"]),
        }
        baselines = [
            self._baseline(bug.bug_id, "profile", remote_profile, remote_profile, operation_id),
            self._baseline(bug.bug_id, "status", remote_status, remote_status, operation_id),
            self._baseline(
                bug.bug_id,
                "assignee",
                {"userId": resolved["assignee_user_id"]},
                {"account": snapshot["assignedTo"]},
                operation_id,
            ),
        ]
        if not description["hasImages"]:
            # 带图正文按 R30/R41 只导入文本：描述组不建基线，待文件管线补齐后由反向拉取确认。
            baselines.append(
                self._baseline(
                    bug.bug_id,
                    "description",
                    {"digest": description["digest"]},
                    {"digest": description["digest"]},
                    operation_id,
                )
            )
        for _ in range(3):
            bug.bug_no = await self.repository.next_bug_no(project_id)
            self.repository.add(bug)
            self.repository.add_activity(create_activity)
            self.repository.add_activity(sync_activity)
            self.session.add(push)
            for baseline in baselines:
                self.session.add(baseline)
            try:
                await self.repository.commit()
            except IntegrityError as exc:
                await self.repository.rollback()
                if _bug_no_conflict(exc):
                    continue
                if _identity_conflict(exc):
                    return await self._conflict_result(
                        project_id, instance_url, int(snapshot["remoteBugId"]), snapshot["title"]
                    )
                raise
            break
        else:
            return import_result(
                snapshot["remoteBugId"], "failed", error_message="Bug 编号分配冲突，请重试"
            )
        return import_result(
            snapshot["remoteBugId"],
            "success",
            bug_id=bug.bug_id,
            bug_no=bug.bug_no,
            title=bug.title,
            pending=pending,
        )

    async def _conflict_result(
        self, project_id: str, instance_url: str, remote_bug_id: int, title: str
    ) -> BugImportResult:
        """唯一约束兜底：区分本项目重复与其他项目占用（R12，不泄露去向）。"""
        link = await remote_link(self.session, instance_key(instance_url), remote_bug_id)
        if link is not None:
            bug = await self.repository.get_bug(link.bug_id)
            if bug is not None and bug.project_id == project_id:
                return import_result(
                    remote_bug_id,
                    "already_linked",
                    bug_id=bug.bug_id,
                    bug_no=bug.bug_no,
                    title=bug.title,
                    error_message="该禅道 Bug 已导入过，请从现有平台 Bug 同步",
                )
        return import_result(
            remote_bug_id,
            "conflict",
            title=title,
            error_message="该禅道 Bug 已被其他平台项目关联，不能重复导入",
        )

    @staticmethod
    def _baseline(
        bug_id: str,
        group: str,
        local: dict,
        remote: dict,
        operation_id: str,
    ) -> BugZentaoSyncBaseline:
        return BugZentaoSyncBaseline(
            bug_id=bug_id,
            field_group=group,
            local_snapshot_json=local,
            remote_snapshot_json=remote,
            operation_id=operation_id,
            applied_at=datetime.now(UTC),
        )
