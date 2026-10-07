"""Bug 生命周期：创建自增编号、禅道三主状态与独立确认/解决方案、独立转派、处理记录与动态。

查看要求 bug_read；评论/转派/流转要求 bug_handle；创建/编辑仍要求 write。
责任人可选范围为项目成员（含所有者），与测试单执行人一致。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.enums import (
    BugAction,
    BugActivityKind,
    BugPriority,
    BugRejectReason,
    BugResolution,
    BugSeverity,
    BugStatus,
)
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrBugAssigneeInvalid,
    ErrBugContentRequired,
    ErrBugNotFound,
    ErrBugPriorityInvalid,
    ErrBugRejectReasonInvalid,
    ErrBugRequirementMismatch,
    ErrBugSeverityInvalid,
    ErrBugSourceMismatch,
    ErrBugSprintMismatch,
    ErrBugTransitionInvalid,
    ErrNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.rich_text import (
    extract_file_ids,
    has_rich_text_content,
    sanitize_rich_text,
)
from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.repositories.bug import BugRepository
from testing_agent.schemas.bug import (
    BugActivityResponse,
    BugAttachmentResponse,
    BugResponse,
    BugTransitionRequest,
)
from testing_agent.services.common import dump, list_payload, paged_payload
from testing_agent.services.project_access import ProjectAction, require_project_id

FUNCTION_CASE_TYPE = "function"

# canonical actions are shared with ZenTao; older client actions remain accepted.
TRANSITIONS = {
    ("active", "confirm"): "active",
    ("active", "resolve"): "resolved",
    ("resolved", "close"): "closed",
    ("resolved", "activate"): "active",
    ("closed", "activate"): "active",
}
LEGACY_ACTIONS = {
    "submit_fix": "resolve",
    "reject": "resolve",
    "regression_pass": "close",
    "regression_fail": "activate",
    "reopen": "activate",
}
LEGACY_RESOLUTIONS = {
    "by_design": "bydesign",
    "not_reproducible": "notrepro",
    "deferred": "postponed",
}


REJECT_REASON_LABELS = {
    BugRejectReason.BY_DESIGN.value: "设计如此",
    BugRejectReason.NOT_REPRODUCIBLE.value: "无法复现",
    BugRejectReason.DEFERRED.value: "遗留",
}


def _bug_no_conflict(exc: IntegrityError) -> bool:
    detail = str(exc.orig)
    return "uk_bugs_project_bug_no" in detail or (
        "UNIQUE constraint failed: bugs.project_id, bugs.bug_no" in detail
    )


class BugService:
    def __init__(self, repository: BugRepository, files=None):
        self.repository = repository
        self.files = files

    async def options(self, user_id: str, project_id: str) -> dict:
        await require_project_id(self.repository.session, user_id, project_id, "bug_read")
        return await self.repository.bug_options(project_id)

    async def get_accessible_entity(
        self, user_id: str, bug_id: str, *, action: ProjectAction = "bug_read"
    ) -> Bug:
        bug = await self.repository.get_bug(bug_id)
        if bug is None:
            raise ErrBugNotFound()
        await require_project_id(self.repository.session, user_id, bug.project_id, action)
        return bug

    async def _is_assignable_member(self, project_id: str, user_id: str) -> bool:
        """项目所有者不是 project_members 行，因此单独判断。"""
        project = await self.repository.get_project(project_id)
        if project is None:
            return False
        if project.user_id == user_id:
            return True
        return await self.repository.get_project_member(project_id, user_id) is not None

    @staticmethod
    def _validate_severity(value: str) -> str:
        value = value.strip()
        if value not in BugSeverity.values():
            raise ErrBugSeverityInvalid()
        return value

    @staticmethod
    def _validate_priority(value: str) -> str:
        value = value.strip()
        if value not in BugPriority.values():
            raise ErrBugPriorityInvalid()
        return value

    async def _resolve_optional_sprint(self, project_id: str, sprint_id: str) -> str:
        sprint_id = sprint_id.strip()
        if not sprint_id:
            return ""
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrBugSprintMismatch()
        return sprint_id

    async def _resolve_optional_requirement(self, project_id: str, requirement_id: str) -> str:
        requirement_id = requirement_id.strip()
        if not requirement_id:
            return ""
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrBugRequirementMismatch()
        return requirement_id

    async def _resolve_source(self, project_id: str, body: Any) -> dict[str, str]:
        """从执行记录提交时校验归属并快照测试单/用例名称，防删后失联。"""
        entry_id = body.source_entry_id.strip()
        order_id = body.source_order_id.strip()
        if not entry_id and not order_id:
            return {}
        if entry_id:
            entry = await self.repository.get_entry(entry_id)
            if entry is None:
                raise ErrNotFound()
            order = await self.repository.get_order(entry.order_id)
            if order is None or order.project_id != project_id:
                raise ErrBugSourceMismatch()
            case_title = ""
            if entry.case_id and entry.case_type == FUNCTION_CASE_TYPE:
                case_title = await self.repository.get_case_title(entry.case_id)
            return {
                "source_order_id": order.order_id,
                "source_entry_id": entry.entry_id,
                "source_case_id": entry.case_id,
                "source_order_name": order.name,
                "source_case_title": case_title,
            }
        order = await self.repository.get_order(order_id)
        if order is None or order.project_id != project_id:
            raise ErrBugSourceMismatch()
        return {"source_order_id": order.order_id, "source_order_name": order.name}

    async def _attach_files(
        self, user_id: str, project_id: str, bug_id: str, file_ids: list[str]
    ) -> list[dict[str, str]]:
        if not file_ids:
            return []
        if self.files is None:
            raise ErrBadRequest()
        added: list[dict[str, str]] = []
        for file_id in file_ids:
            row = await self.files.attach(
                user_id, file_id, project_id, "bug", bug_id, purpose="attachment"
            )
            added.append({"fileId": row.file_id, "filename": row.filename})
        return added

    def _record(self, bug: Bug, **fields: Any) -> None:
        self.repository.add_activity(BugActivity(activity_id=new_id(), bug_id=bug.bug_id, **fields))

    async def create(self, user_id: str, project_id: str, body: Any) -> dict:
        await require_project_id(self.repository.session, user_id, project_id, "write")
        severity = self._validate_severity(body.severity)
        priority = self._validate_priority(body.priority)
        assignee = body.assignee_user_id.strip()
        # 创建时必须指定责任人；流转时不要求再次填写。
        if not assignee or not await self._is_assignable_member(project_id, assignee):
            raise ErrBugAssigneeInvalid()
        found_sprint_id = body.found_sprint_id.strip()
        found = await self.repository.get_sprint(found_sprint_id)
        if found is None or found.project_id != project_id:
            raise ErrBugSprintMismatch()
        planned_fix_sprint_id = await self._resolve_optional_sprint(
            project_id, body.planned_fix_sprint_id
        )
        requirement_id = await self._resolve_optional_requirement(project_id, body.requirement_id)
        source = await self._resolve_source(project_id, body)
        description_html = sanitize_rich_text(body.description_html)
        if not has_rich_text_content(description_html):
            raise AppError(400, "请填写问题描述", 400)
        image_file_ids = extract_file_ids(description_html)
        bug = Bug(
            bug_id=new_id(),
            bug_no=0,
            project_id=project_id,
            title=body.title,
            description_html=description_html,
            status=BugStatus.ACTIVE.value,
            severity=severity,
            priority=priority,
            reporter_user_id=user_id,
            assignee_user_id=assignee,
            found_sprint_id=found_sprint_id,
            planned_fix_sprint_id=planned_fix_sprint_id,
            requirement_id=requirement_id,
            **source,
        )
        activity = BugActivity(
            activity_id=new_id(),
            bug_id=bug.bug_id,
            kind=BugActivityKind.STATUS_CHANGE.value,
            actor_user_id=user_id,
            action="create",
            from_status="",
            to_status=BugStatus.ACTIVE.value,
        )
        for _ in range(3):
            bug.bug_no = await self.repository.next_bug_no(project_id)
            self.repository.add(bug)
            self.repository.add_activity(activity)
            await self._attach_files(user_id, project_id, bug.bug_id, image_file_ids)
            await self._attach_files(user_id, project_id, bug.bug_id, body.attachment_file_ids)
            try:
                await self.repository.commit()
                break
            except IntegrityError as exc:
                await self.repository.rollback()
                if not _bug_no_conflict(exc):
                    raise
        else:
            raise AppError(409, "Bug 编号分配冲突，请重试", 409)
        return await self._dump_detail(bug)

    async def list_project(
        self,
        user_id: str,
        project_id: str,
        *,
        statuses: list[str],
        confirmed: bool | None,
        resolution: str,
        severity: str,
        assignee_user_id: str,
        sprint_id: str,
        sprint_filter: str,
        source_entry_id: str,
        keyword: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, "bug_read")
        resolution = resolution.strip()
        if set(statuses) - BugStatus.values() or (
            resolution and resolution not in BugResolution.values()
        ):
            raise AppError(400, "Bug 状态或解决方案筛选不合法", 400)
        rows, total = await self.repository.list_by_query(
            project_id,
            statuses=statuses,
            confirmed=confirmed,
            resolution=resolution.strip(),
            severity=severity.strip(),
            assignee_user_id=assignee_user_id.strip(),
            sprint_id=sprint_id.strip(),
            sprint_filter=sprint_filter.strip(),
            source_entry_id=source_entry_id.strip(),
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
        return paged_payload([dump(BugResponse, bug) for bug in rows], total)

    async def get(self, user_id: str, bug_id: str) -> dict:
        return await self._dump_detail(
            await self.get_accessible_entity(user_id, bug_id, action="bug_read")
        )

    async def _dump_detail(self, bug: Bug) -> dict:
        await self.repository.resolve_requirement_names([bug])
        data = dump(BugResponse, bug)
        attachments: list[Any] = []
        if self.files is not None:
            attachments = [
                dump(BugAttachmentResponse, row)
                for row in await self.files.list_by_resource(bug.project_id, "bug", bug.bug_id)
            ]
        data["attachments"] = attachments
        return data

    async def transition(self, user_id: str, bug_id: str, body: BugTransitionRequest) -> dict:
        bug = await self.get_accessible_entity(user_id, bug_id, action="bug_handle")
        # Lock and refresh after checking permissions, so decisions use current state.
        await self.repository.session.refresh(bug, with_for_update=True)
        action = body.action.strip()
        if action not in BugAction.values():
            raise ErrBadRequest()
        canonical_action = LEGACY_ACTIONS.get(action, action)
        target = TRANSITIONS.get((bug.status, canonical_action))
        if target is None or (canonical_action == "confirm" and bug.confirmed):
            raise ErrBugTransitionInvalid()
        if action == "submit_fix" and not bug.confirmed:
            raise ErrBugTransitionInvalid()
        if action in {"regression_pass", "regression_fail"} and bug.resolution != "fixed":
            raise ErrBugTransitionInvalid()
        content = body.content.strip()
        detail: dict[str, Any] = {
            "fromConfirmed": bug.confirmed,
            "toConfirmed": bug.confirmed,
            "fromResolution": bug.resolution,
            "toResolution": bug.resolution,
        }
        resolution = body.resolution.strip()
        resolved_build = body.resolved_build.strip()
        duplicate_bug = body.duplicate_bug
        if action == "reject":
            reason = body.reject_reason.strip()
            if reason not in BugRejectReason.values():
                raise ErrBugRejectReasonInvalid()
            resolution = LEGACY_RESOLUTIONS[reason]
            detail.update(rejectReason=reason, rejectReasonLabel=REJECT_REASON_LABELS[reason])
        elif canonical_action != "confirm" and not content:
            raise ErrBugContentRequired()
        if canonical_action == "resolve":
            if action == "submit_fix":
                resolution = "fixed"
            if resolution not in BugResolution.values():
                raise AppError(400, "请选择有效的解决方案", 400)
            if resolution != "fixed" and resolved_build:
                raise AppError(400, "仅已修复可以填写解决版本", 400)
            if resolution == "fixed" and not resolved_build:
                raise AppError(400, "已修复必须填写解决版本", 400)
            if resolution == "duplicate":
                from sqlalchemy import select

                duplicate = await self.repository.session.scalar(
                    select(Bug).where(Bug.id == duplicate_bug, Bug.project_id == bug.project_id)
                )
                if duplicate is None or duplicate.bug_id == bug.bug_id:
                    raise AppError(400, "重复 Bug 必须是当前项目的另一条 Bug", 400)
            elif duplicate_bug:
                raise AppError(400, "仅重复 Bug 解决方案可填写重复 Bug ID", 400)
            bug.resolution = resolution
            bug.resolved_build = resolved_build if resolution == "fixed" else ""
            bug.duplicate_bug = duplicate_bug if resolution == "duplicate" else 0
            detail.update(resolvedBuild=bug.resolved_build, duplicateBug=bug.duplicate_bug)
        elif resolution or resolved_build or duplicate_bug:
            raise AppError(400, "只有解决操作可以设置解决方案、版本和重复 Bug", 400)
        if canonical_action == "confirm":
            bug.confirmed = True
        elif canonical_action == "activate":
            bug.resolution = ""
            bug.resolved_build = ""
            bug.duplicate_bug = 0
            bug.activated_count += 1
        from_status = bug.status
        bug.status = target
        detail.update(toConfirmed=bug.confirmed, toResolution=bug.resolution)
        self._record(
            bug,
            kind=BugActivityKind.STATUS_CHANGE.value,
            actor_user_id=user_id,
            action=action,
            from_status=from_status,
            to_status=target,
            content=content,
            detail_json=detail,
        )
        await self.repository.commit()
        return await self._dump_detail(bug)

    async def transfer(self, user_id: str, bug_id: str, body: Any) -> dict:
        bug = await self.get_accessible_entity(user_id, bug_id, action="bug_handle")
        assignee = body.assignee_user_id.strip()
        if not assignee or not await self._is_assignable_member(bug.project_id, assignee):
            raise ErrBugAssigneeInvalid()
        if assignee != bug.assignee_user_id:
            previous = bug.assignee_user_id
            bug.assignee_user_id = assignee
            self._record(
                bug,
                kind=BugActivityKind.TRANSFER.value,
                actor_user_id=user_id,
                action="transfer",
                detail_json={"fromUserId": previous, "toUserId": assignee},
            )
            await self.repository.commit()
        return await self._dump_detail(bug)

    async def update(self, user_id: str, bug_id: str, body: dict[str, Any]) -> dict:
        """编辑基本信息与描述：不改变状态；计划修复迭代保留发现迭代。"""
        bug = await self.get_accessible_entity(user_id, bug_id, action="write")
        changes: list[dict[str, str]] = []

        async def apply(field: str, label: str, new_value: Any, resolver=None) -> None:
            old_value = getattr(bug, field)
            if resolver is not None:
                new_value = await resolver(new_value)
            if new_value != old_value:
                changes.append({"field": label, "from": str(old_value), "to": str(new_value)})
                setattr(bug, field, new_value)

        if "title" in body:
            await apply("title", "title", body["title"])
        if "severity" in body:
            await apply("severity", "severity", self._validate_severity(body["severity"]))
        if "priority" in body:
            await apply("priority", "priority", self._validate_priority(body["priority"]))
        if "planned_fix_sprint_id" in body:
            await apply(
                "planned_fix_sprint_id",
                "plannedFixSprintId",
                body["planned_fix_sprint_id"],
                resolver=lambda value: self._resolve_optional_sprint(
                    bug.project_id, str(value or "")
                ),
            )
        if "requirement_id" in body:
            await apply(
                "requirement_id",
                "requirementId",
                body["requirement_id"],
                resolver=lambda value: self._resolve_optional_requirement(
                    bug.project_id, str(value or "")
                ),
            )
        description_changed = False
        if "description_html" in body:
            cleaned = sanitize_rich_text(str(body["description_html"] or ""))
            if not has_rich_text_content(cleaned):
                raise AppError(400, "请填写问题描述", 400)
            if cleaned != bug.description_html:
                changes.append(
                    {
                        "field": "descriptionHtml",
                        "from": bug.description_html,
                        "to": cleaned,
                    }
                )
                bug.description_html = cleaned
                description_changed = True
        removed = []
        inline_ids = set(extract_file_ids(bug.description_html))
        for file_id in dict.fromkeys(body.get("removed_attachment_file_ids") or []):
            if self.files is None:
                raise ErrBadRequest()
            row = await self.files.get(file_id, lock=True)
            if (row.project_id, row.resource_type, row.resource_id, row.status) != (
                bug.project_id,
                "bug",
                bug.bug_id,
                "attached",
            ):
                raise AppError(400, "附件不属于当前 Bug", 400)
            if file_id in inline_ids:
                raise AppError(400, "请先从问题描述中移除该图片", 400)
            # Removing current evidence must not invalidate previous descriptions
            # or activity records. Keep the Bug association for authorization.
            row.status = "archived"
            removed.append({"fileId": row.file_id, "filename": row.filename})
        file_ids = list(body.get("attachment_file_ids") or [])
        if description_changed:
            file_ids += extract_file_ids(bug.description_html)
        added = await self._attach_files(user_id, bug.project_id, bug.bug_id, file_ids)
        if changes:
            self._record(
                bug,
                kind=BugActivityKind.EDIT.value,
                actor_user_id=user_id,
                action="edit",
                detail_json={"changes": changes},
            )
        if added or removed:
            self._record(
                bug,
                kind=BugActivityKind.ATTACHMENT.value,
                actor_user_id=user_id,
                action="attachment",
                detail_json={"addedFiles": added, "removedFiles": removed},
            )
        await self.repository.commit()
        return await self._dump_detail(bug)

    async def add_comment(self, user_id: str, bug_id: str, content: str) -> dict:
        bug = await self.get_accessible_entity(user_id, bug_id, action="bug_handle")
        self._record(
            bug,
            kind=BugActivityKind.COMMENT.value,
            actor_user_id=user_id,
            action="comment",
            content=content.strip(),
        )
        await self.repository.commit()
        return {}

    async def list_activities(self, user_id: str, bug_id: str) -> dict[str, Any]:
        bug = await self.get_accessible_entity(user_id, bug_id, action="bug_read")
        rows = await self.repository.list_activities(bug.bug_id)
        return list_payload([dump(BugActivityResponse, row) for row in rows])
