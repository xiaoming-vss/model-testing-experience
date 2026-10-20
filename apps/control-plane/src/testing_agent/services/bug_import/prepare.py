from typing import Any

from testing_agent.domain import zentao_bug_mapping as mapping
from testing_agent.repositories.bug import BugRepository
from testing_agent.repositories.zentao_bug_import import (
    assignable_member,
    duplicate_local_id,
    find_binding,
)
from testing_agent.schemas.bug_zentao_import import (
    ZentaoBugImportItemRequest,
    ZentaoImportSnapshot,
)
from testing_agent.services.bug_import.contracts import (
    BugImportResult,
    ImportDescription,
    ImportStatus,
    PreparedBugImport,
    ResolvedBugImport,
    import_result,
)
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_mcp import ZentaoMcpConnection


class BugImportPreparation:
    def __init__(self, repository: BugRepository) -> None:
        self.repository = repository

    async def preview(
        self,
        detail: dict[str, Any],
        access: ZentaoMcpConnection,
        project_id: str,
        remote_bug_id: int,
    ) -> dict[str, Any]:
        try:
            snapshot = mapping.remote_snapshot(detail)
        except ValueError as exc:
            return {
                "remote_bug_id": remote_bug_id,
                "state": "invalid",
                "error_message": str(exc),
            }
        if snapshot["deleted"]:
            return {
                "remote_bug_id": remote_bug_id,
                "state": "invalid",
                "error_message": "禅道 Bug 不存在或已删除",
            }
        pending: list[dict[str, str]] = [
            {"field": "assigneeUserId", "reason": "请选择平台责任人（Q05：不按账号自动映射）"}
        ]
        severity = mapping.map_severity(snapshot["severity"])
        if severity is None:
            pending.append({"field": "severity", "reason": "禅道严重程度无法映射，请人工选择"})
        priority = mapping.map_priority(snapshot["priority"])
        if priority is None:
            pending.append({"field": "priority", "reason": "禅道优先级无法映射，请人工选择"})
        status_fields = mapping.map_status(
            snapshot["status"],
            snapshot["confirmed"],
            snapshot["resolution"],
            snapshot["resolvedBuild"],
        )
        state = "ready"
        if status_fields is None:
            state = "pending"
            pending.append({"field": "status", "reason": "禅道状态或解决方案无法映射"})
        description = mapping.remote_description(detail.get("steps"))
        if description["hasImages"] and description["hasContent"]:
            # R41：先导入文本并标记待补，图片随文件管线反向导入后再完成描述组（R30）。
            pending.append(
                {
                    "field": "description",
                    "reason": (
                        "正文包含图片：本次先导入文本，图片待文件管线反向导入后补齐，描述组暂不建立基线"
                    ),
                }
            )
        elif not description["hasContent"]:
            state = "pending"
            reason = (
                "正文仅包含图片且无有效文本，需等待文件管线反向导入"
                if description["hasImages"]
                else "远端描述没有有效内容"
            )
            pending.append({"field": "description", "reason": reason})
        sprint = await self._sprint_for_execution(
            project_id, access.base_url, int(snapshot["execution"])
        )
        if sprint is None:
            pending.append({"field": "foundSprintId", "reason": "远端执行未绑定本地迭代，请选择"})
        requirement = await self._requirement_for_story(
            project_id, access.base_url, int(snapshot["story"])
        )
        duplicate_local = await duplicate_local_id(
            self.repository,
            project_id,
            instance_key(access.base_url),
            int(snapshot["duplicateBug"]),
        )
        if int(snapshot["duplicateBug"]) and duplicate_local is None:
            pending.append(
                {
                    "field": "duplicateBug",
                    "reason": "远端重复 Bug 无法解析为同项目平台 Bug，导入后该字段留空",
                }
            )
        converted = {
            "severity": severity,
            "priority": priority,
            **(status_fields or {}),
            "duplicateBugId": duplicate_local,
            "foundSprintId": sprint[0] if sprint else "",
            "foundSprintName": sprint[1] if sprint else "",
            "requirementId": requirement[0] if requirement else "",
            "requirementName": requirement[1] if requirement else "",
        }
        return {
            "remote_bug_id": remote_bug_id,
            "state": state,
            "title": snapshot["title"],
            "snapshot": snapshot,
            "converted": converted,
            "description": {
                "hasImages": description["hasImages"],
                "hasContent": description["hasContent"],
            },
            "pending": pending,
        }

    async def prepare(
        self,
        detail: dict[str, Any],
        access: ZentaoMcpConnection,
        project_id: str,
        item: ZentaoBugImportItemRequest,
    ) -> PreparedBugImport | BugImportResult:
        try:
            snapshot = mapping.remote_snapshot(detail)
        except ValueError as exc:
            return import_result(item.remote_bug_id, "failed", error_message=str(exc))
        if snapshot["deleted"]:
            return import_result(
                item.remote_bug_id, "failed", error_message="禅道 Bug 不存在或已删除"
            )
        if snapshot["remoteBugId"] != item.remote_bug_id:
            return import_result(
                item.remote_bug_id, "failed", error_message="禅道 Bug 详情编号不匹配"
            )
        pending: list[dict[str, str]] = []
        severity = item.severity or mapping.map_severity(snapshot["severity"])
        if severity is None:
            return import_result(
                item.remote_bug_id, "failed", error_message="严重程度未指定且禅道值无法映射"
            )
        priority = item.priority or mapping.map_priority(snapshot["priority"])
        if priority is None:
            return import_result(
                item.remote_bug_id, "failed", error_message="优先级未指定且禅道值无法映射"
            )
        status_fields = mapping.map_status(
            snapshot["status"],
            snapshot["confirmed"],
            snapshot["resolution"],
            snapshot["resolvedBuild"],
        )
        if status_fields is None:
            return import_result(
                item.remote_bug_id, "failed", error_message="禅道状态或解决方案无法映射（R27）"
            )
        description = mapping.remote_description(detail.get("steps"))
        if description["hasImages"] and not description["hasContent"]:
            return import_result(
                item.remote_bug_id,
                "pending",
                error_message="正文仅包含图片且无有效文本，需等待文件管线反向导入（R30）",
            )
        if not description["hasContent"]:
            return import_result(item.remote_bug_id, "failed", error_message="远端描述没有有效内容")
        if description["hasImages"]:
            # R41：文本先行导入，图片组待文件管线；描述组不建立基线，避免误标为已同步（R30）。
            pending.append(
                {
                    "field": "description",
                    "reason": (
                        "正文包含图片：已先导入文本，图片待文件管线反向导入后补齐，描述组待补建基线"
                    ),
                }
            )
        if not await assignable_member(self.repository, project_id, item.assignee_user_id):
            return import_result(
                item.remote_bug_id, "failed", error_message="责任人必须是当前项目可指派的成员"
            )
        found_sprint = await self.repository.get_sprint(item.found_sprint_id)
        if found_sprint is None or found_sprint.project_id != project_id:
            return import_result(
                item.remote_bug_id, "failed", error_message="发现迭代必须属于当前项目"
            )
        requirement_id = ""
        if item.requirement_id:
            requirement = await self.repository.get_requirement(item.requirement_id)
            sprint = (
                None
                if requirement is None
                else await self.repository.get_sprint(requirement.sprint_id)
            )
            if requirement is None or sprint is None or sprint.project_id != project_id:
                return import_result(
                    item.remote_bug_id, "failed", error_message="所属需求必须属于当前项目"
                )
            requirement_id = requirement.requirement_id
        duplicate_local = await duplicate_local_id(
            self.repository,
            project_id,
            instance_key(access.base_url),
            int(snapshot["duplicateBug"]),
        )
        if int(snapshot["duplicateBug"]) and duplicate_local is None:
            pending.append(
                {"field": "duplicateBug", "reason": "远端重复 Bug 无法解析为同项目平台 Bug，已留空"}
            )
        duplicate_bug = duplicate_local if status_fields["resolution"] == "duplicate" else 0
        return PreparedBugImport(
            snapshot=ZentaoImportSnapshot(
                remoteBugId=snapshot["remoteBugId"],
                title=snapshot["title"],
                severity=snapshot["severity"],
                priority=snapshot["priority"],
                status=snapshot["status"],
                confirmed=snapshot["confirmed"],
                resolution=snapshot["resolution"],
                resolvedBuild=snapshot["resolvedBuild"],
                duplicateBug=snapshot["duplicateBug"],
                activatedCount=snapshot["activatedCount"],
                execution=snapshot["execution"],
                story=snapshot["story"],
                project=snapshot["project"],
                assignedTo=snapshot["assignedTo"],
                openedBy=snapshot["openedBy"],
                openedDate=snapshot["openedDate"],
                deleted=snapshot["deleted"],
            ),
            status=ImportStatus(
                status=status_fields["status"],
                confirmed=status_fields["confirmed"],
                resolution=status_fields["resolution"],
                resolvedBuild=status_fields["resolvedBuild"],
            ),
            description=ImportDescription(
                sanitized=description["sanitized"],
                digest=description["digest"],
                textOnly=description["textOnly"],
                textOnlyDigest=description["textOnlyDigest"],
                hasImages=description["hasImages"],
                hasContent=description["hasContent"],
            ),
            resolved=ResolvedBugImport(
                severity=severity,
                priority=priority,
                assignee_user_id=item.assignee_user_id,
                found_sprint_id=found_sprint.sprint_id,
                requirement_id=requirement_id,
                duplicate_bug=duplicate_bug,
            ),
            pending=pending,
        )

    async def _sprint_for_execution(
        self, project_id: str, instance_url: str, execution_id: int
    ) -> tuple[str, str] | None:
        if not execution_id:
            return None
        binding = await find_binding(
            self.repository.session,
            "sprint",
            "execution",
            str(execution_id),
            instance_key(instance_url),
        )
        if binding is None:
            return None
        sprint = await self.repository.get_sprint(binding.local_resource_id)
        if sprint is None or sprint.project_id != project_id:
            return None
        return sprint.sprint_id, sprint.name

    async def _requirement_for_story(
        self, project_id: str, instance_url: str, story_id: int
    ) -> tuple[str, str] | None:
        if not story_id:
            return None
        binding = await find_binding(
            self.repository.session,
            "requirement",
            "story",
            str(story_id),
            instance_key(instance_url),
        )
        if binding is None:
            return None
        requirement = await self.repository.get_requirement(binding.local_resource_id)
        if requirement is None:
            return None
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None or sprint.project_id != project_id:
            return None
        return requirement.requirement_id, requirement.name
