"""禅道新建 Bug 手动导入：候选列表、预览与本地事务落库。

远端只读（R34）：候选与详情通过项目 MCP 和操作者本人 Token 读取；本地
Bug、禅道关联与字段组基线在同一个本地事务创建（R40）。转换统一使用
`domain.zentao_bug_mapping`，与反向拉取共用同一口径（R20）。
"""

from datetime import UTC, datetime
from hashlib import sha256
from re import I as _RE_I
from re import finditer as _re_finditer
from re import search as _re_search
from re import sub as _re_sub

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from testing_agent.core.enums import BugActivityKind
from testing_agent.core.errors import AppError
from testing_agent.core.sid import new_id
from testing_agent.domain import zentao_bug_mapping as mapping
from testing_agent.domain.rich_text import has_rich_text_content, sanitize_rich_text
from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.bug_zentao_sync_baseline import BugZentaoSyncBaseline
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.schemas.bug_zentao_import import (
    ZentaoBugCandidateItem,
    ZentaoBugImportItemRequest,
    ZentaoBugImportPreview,
    ZentaoBugImportResult,
)
from testing_agent.services.common import dump, paged_payload
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.project_access import require_project_id
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_mcp import ZentaoMcpAccess, normalize_list

PAGE_LIMIT = 100
PAGE_COUNT_LIMIT = 100


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


class ZentaoBugImportService:
    def __init__(self, bugs, connections, *, client_factory=None):
        self.bugs = bugs
        self.repository = bugs.repository
        self.session = bugs.repository.session
        self.connections = connections
        self.client_factory = client_factory or McpClient

    # ------------------------------------------------------------------ access

    async def _access(self, user_id: str, project_id: str):
        """写入权限 + 项目级禅道绑定 + 本人授权与实例核对（R07/R08/R15）。"""
        await require_project_id(self.session, user_id, project_id, "write")
        binding = await self.session.scalar(
            select(ResourceBinding).where(
                ResourceBinding.provider == "zentao",
                ResourceBinding.status == "active",
                ResourceBinding.local_resource_type == "project",
                ResourceBinding.local_resource_id == project_id,
            )
        )
        if binding is None:
            raise AppError(400, "当前项目尚未绑定禅道项目，请先完成资源绑定", 400)
        access = await ZentaoMcpAccess(self.connections).resolve(
            user_id, project_id, expected_instance=binding.instance_url
        )
        return access, binding

    async def _fetch_detail(self, client, remote_bug_id: int) -> dict:
        data = await client.call("get_bugs_bugID", {"bugID": remote_bug_id})
        bug = data.get("bug", {})
        if not isinstance(bug, dict):
            raise McpCallError("禅道 Bug 详情格式异常")
        return bug

    async def _linked_remote_ids(self, instance_url: str, remote_ids: list[int]) -> set[int]:
        if not remote_ids:
            return set()
        rows = await self.session.scalars(
            select(BugZentaoPush.remote_bug_id).where(
                BugZentaoPush.instance_key == instance_key(instance_url),
                BugZentaoPush.remote_bug_id.in_(remote_ids),
            )
        )
        return {int(value) for value in rows}

    async def _paged_remote_bugs(self, client, tool: str, arguments: dict) -> list[dict]:
        items: list[dict] = []
        seen: set[str] = set()
        for page in range(1, PAGE_COUNT_LIMIT + 1):
            data = await client.call(
                tool,
                {
                    **arguments,
                    "browseType": "all",
                    "orderBy": "id_asc",
                    "pageID": page,
                    "recPerPage": PAGE_LIMIT,
                },
            )
            batch, total = normalize_list(data, "bugs")
            if any(item["id"] in seen for item in batch):
                raise McpCallError("禅道 Bug 分页重复，已停止读取")
            seen.update(item["id"] for item in batch)
            items.extend(batch)
            complete = total is not None and len(items) >= total
            if complete or (total is None and len(batch) < PAGE_LIMIT):
                return items
            if not batch:
                raise McpCallError("禅道 Bug 分页数据不完整")
        raise McpCallError("禅道 Bug 超过查询上限，请缩小筛选范围")

    async def _execution_for_sprint(
        self, project_id: str, instance_url: str, sprint_id: str
    ) -> int:
        """当前迭代绑定的禅道执行编号；未绑定返回 0（回退项目范围）。"""
        if not sprint_id:
            return 0
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None or sprint.project_id != project_id:
            return 0
        binding = await self.session.scalar(
            select(ResourceBinding).where(
                ResourceBinding.provider == "zentao",
                ResourceBinding.status == "active",
                ResourceBinding.local_resource_type == "sprint",
                ResourceBinding.local_resource_id == sprint_id,
                ResourceBinding.remote_resource_type == "execution",
                ResourceBinding.instance_key == instance_key(instance_url),
            )
        )
        return int(binding.remote_resource_id) if binding else 0

    # -------------------------------------------------------------- candidates

    async def candidates(
        self,
        user_id: str,
        project_id: str,
        *,
        sprint_id: str = "",
        status: str = "",
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """按当前迭代绑定的执行整套查询候选；迭代未绑定执行时直接提示（用户确认）。"""
        access, binding = await self._access(user_id, project_id)
        execution_id = await self._execution_for_sprint(project_id, access.base_url, sprint_id)
        if sprint_id and not execution_id:
            raise AppError(400, "当前迭代未绑定禅道执行，请先在资源绑定中完成迭代绑定", 400)
        try:
            async with self.client_factory(access.endpoint, access.token) as client:
                if execution_id:
                    rows = await self._paged_remote_bugs(
                        client,
                        "get_executions_executionID_bugs",
                        {"executionID": execution_id},
                    )
                    scope = "execution"
                else:
                    rows = await self._paged_remote_bugs(
                        client,
                        "get_projects_projectID_bugs",
                        {"projectID": int(binding.remote_resource_id)},
                    )
                    scope = "project"
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc
        wanted = {value.strip() for value in status.split(",") if value.strip()}
        needle = keyword.strip().lower()
        matched = []
        for row in rows:
            if wanted and str(row.get("status") or "").strip() not in wanted:
                continue
            if needle and needle not in str(row.get("title") or "").lower():
                continue
            matched.append(row)
        linked = await self._linked_remote_ids(access.base_url, [int(row["id"]) for row in matched])
        start = (page - 1) * page_size
        slice_rows = matched[start : start + page_size]
        items = []
        for row in slice_rows:
            items.append(
                dump(
                    ZentaoBugCandidateItem,
                    {
                        "remote_bug_id": int(row["id"]),
                        "title": str(row.get("title") or ""),
                        "status": str(row.get("status") or "").strip(),
                        "severity": str(row.get("severity") or "").strip(),
                        "priority": str(row.get("pri") or row.get("priority") or "").strip(),
                        "assigned_to": str(row.get("assignedTo") or "").strip(),
                        "opened_by": str(row.get("openedBy") or "").strip(),
                        "opened_date": str(row.get("openedDate") or "").strip(),
                        "execution": _optional_remote_id(row.get("execution")),
                        "story": _optional_remote_id(row.get("story")),
                        "linked": int(row["id"]) in linked,
                    },
                )
            )
        return {
            "scope": scope,
            "executionId": execution_id or None,
            **paged_payload(items, len(matched)),
        }

    # ----------------------------------------------------------------- preview

    async def preview(self, user_id: str, project_id: str, remote_bug_ids: list[int]) -> dict:
        access, _ = await self._access(user_id, project_id)
        results: list[dict] = []
        try:
            async with self.client_factory(access.endpoint, access.token) as client:
                for remote_bug_id in dict.fromkeys(remote_bug_ids):
                    results.append(
                        await self._preview_one(client, access, project_id, remote_bug_id)
                    )
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc
        return {"items": [dump(ZentaoBugImportPreview, item) for item in results]}

    async def _preview_one(self, client, access, project_id: str, remote_bug_id: int) -> dict:
        detail = await self._fetch_detail(client, remote_bug_id)
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
        duplicate_local = await self._duplicate_local_id(
            project_id, access.base_url, int(snapshot["duplicateBug"])
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

    async def _sprint_for_execution(
        self, project_id: str, instance_url: str, execution_id: int
    ) -> tuple[str, str] | None:
        if not execution_id:
            return None
        binding = await self._binding("sprint", "execution", str(execution_id), instance_url)
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
        binding = await self._binding("requirement", "story", str(story_id), instance_url)
        if binding is None:
            return None
        requirement = await self.repository.get_requirement(binding.local_resource_id)
        if requirement is None:
            return None
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None or sprint.project_id != project_id:
            return None
        return requirement.requirement_id, requirement.name

    async def _binding(
        self, local_type: str, remote_type: str, remote_id: str, instance_url: str
    ) -> ResourceBinding | None:
        row = await self.session.scalar(
            select(ResourceBinding).where(
                ResourceBinding.provider == "zentao",
                ResourceBinding.status == "active",
                ResourceBinding.local_resource_type == local_type,
                ResourceBinding.remote_resource_type == remote_type,
                ResourceBinding.remote_resource_id == remote_id,
                ResourceBinding.instance_key == instance_key(instance_url),
            )
        )
        return row

    async def _duplicate_local_id(
        self, project_id: str, instance_url: str, remote_bug_id: int
    ) -> int | None:
        return await duplicate_local_id(self.repository, project_id, instance_url, remote_bug_id)

    # ------------------------------------------------------------------ import

    async def import_bugs(
        self,
        user_id: str,
        project_id: str,
        request_id: str,
        items: list[ZentaoBugImportItemRequest],
    ) -> dict:
        access, binding = await self._access(user_id, project_id)
        results: list[dict] = []
        seen: set[int] = set()
        try:
            async with self.client_factory(access.endpoint, access.token) as client:
                for item in items:
                    if item.remote_bug_id in seen:
                        results.append(
                            self._result(
                                item.remote_bug_id,
                                "failed",
                                error_message="同一请求中存在重复的禅道 Bug",
                            )
                        )
                        continue
                    seen.add(item.remote_bug_id)
                    results.append(
                        await self._import_one(
                            client, access, binding, user_id, project_id, request_id, item
                        )
                    )
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc
        return {"items": [dump(ZentaoBugImportResult, item) for item in results]}

    async def _import_one(
        self,
        client,
        access,
        binding,
        user_id: str,
        project_id: str,
        request_id: str,
        item: ZentaoBugImportItemRequest,
    ) -> dict:
        operation_id = f"{request_id}:{item.remote_bug_id}"
        replayed = await self._replay(operation_id)
        if replayed is not None:
            return replayed
        detail = await self._fetch_detail(client, item.remote_bug_id)
        try:
            snapshot = mapping.remote_snapshot(detail)
        except ValueError as exc:
            return self._result(item.remote_bug_id, "failed", error_message=str(exc))
        if snapshot["deleted"]:
            return self._result(
                item.remote_bug_id, "failed", error_message="禅道 Bug 不存在或已删除"
            )
        if snapshot["remoteBugId"] != item.remote_bug_id:
            return self._result(
                item.remote_bug_id, "failed", error_message="禅道 Bug 详情编号不匹配"
            )
        pending: list[dict[str, str]] = []
        severity = item.severity or mapping.map_severity(snapshot["severity"])
        if severity is None:
            return self._result(
                item.remote_bug_id, "failed", error_message="严重程度未指定且禅道值无法映射"
            )
        priority = item.priority or mapping.map_priority(snapshot["priority"])
        if priority is None:
            return self._result(
                item.remote_bug_id, "failed", error_message="优先级未指定且禅道值无法映射"
            )
        status_fields = mapping.map_status(
            snapshot["status"],
            snapshot["confirmed"],
            snapshot["resolution"],
            snapshot["resolvedBuild"],
        )
        if status_fields is None:
            return self._result(
                item.remote_bug_id, "failed", error_message="禅道状态或解决方案无法映射（R27）"
            )
        description = mapping.remote_description(detail.get("steps"))
        if description["hasImages"] and not description["hasContent"]:
            return self._result(
                item.remote_bug_id,
                "pending",
                error_message="正文仅包含图片且无有效文本，需等待文件管线反向导入（R30）",
            )
        if not description["hasContent"]:
            return self._result(item.remote_bug_id, "failed", error_message="远端描述没有有效内容")
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
        if not await self._assignable(project_id, item.assignee_user_id):
            return self._result(
                item.remote_bug_id, "failed", error_message="责任人必须是当前项目可指派的成员"
            )
        found_sprint = await self.repository.get_sprint(item.found_sprint_id)
        if found_sprint is None or found_sprint.project_id != project_id:
            return self._result(
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
                return self._result(
                    item.remote_bug_id, "failed", error_message="所属需求必须属于当前项目"
                )
            requirement_id = requirement.requirement_id
        duplicate_local = await self._duplicate_local_id(
            project_id, access.base_url, int(snapshot["duplicateBug"])
        )
        if int(snapshot["duplicateBug"]) and duplicate_local is None:
            pending.append(
                {"field": "duplicateBug", "reason": "远端重复 Bug 无法解析为同项目平台 Bug，已留空"}
            )
        duplicate_bug = duplicate_local if status_fields["resolution"] == "duplicate" else 0
        created = await self._create_rows(
            access,
            binding,
            user_id,
            project_id,
            operation_id,
            item,
            snapshot,
            status_fields,
            description,
            {
                "severity": severity,
                "priority": priority,
                "assignee_user_id": item.assignee_user_id,
                "found_sprint_id": found_sprint.sprint_id,
                "requirement_id": requirement_id,
                "duplicate_bug": duplicate_bug,
            },
            pending,
        )
        if created["status"] != "success":
            return created
        # R44-R47：正文与附件在本地创建事务之后拉取（外部等待在长事务之外），
        # 单文件失败只记待处理，不影响已创建的 Bug，可随反向拉取补齐。
        await self._pull_files(
            client,
            access,
            user_id,
            project_id,
            created["bug_id"],
            int(snapshot["remoteBugId"]),
            detail,
            operation_id,
            created,
        )
        return created

    async def _pull_files(
        self,
        client,
        access,
        user_id: str,
        project_id: str,
        bug_id: str,
        remote_bug_id: int,
        detail: dict,
        operation_id: str,
        result: dict,
    ) -> None:
        """拉取远端附件与正文图片（R44-R47），重写正文并按完成度写描述基线。

        只认远端附件清单内、属于本 Bug 的文件；正文里无法解析或拉取失败的
        图片按 R41 记待处理，不冒充完整同步。
        """
        steps = str(detail.get("steps") or "")
        catalog = _attachment_index(detail.get("attachments"))
        targets: dict[int, dict] = dict(catalog)
        for rid in _image_refs(steps):
            targets.setdefault(rid, catalog.get(rid, {}))
        file_map: dict[int, str] = {}
        notes: list[str] = []
        pulled_count = 0
        for rid, meta in sorted(targets.items()):
            local_file_id, error = await self._pull_one(
                client, access, user_id, project_id, bug_id, remote_bug_id, rid, operation_id, meta
            )
            if local_file_id is None:
                notes.append(_file_label(rid, meta, error or "拉取失败"))
                continue
            file_map[rid] = local_file_id
            pulled_count += 1
        rewritten, resolved = _rewrite_images(steps, file_map)
        clean = sanitize_rich_text(rewritten) if rewritten else ""
        bug = await self.repository.get_bug(bug_id)
        if bug is None:
            return
        complete = (
            bool(_image_refs(steps))
            and bool(clean)
            and has_rich_text_content(clean)
            and not [rid for rid in _image_refs(steps) if rid not in file_map]
        )
        if clean and clean != bug.description_html and (resolved or has_rich_text_content(clean)):
            bug.description_html = clean
        if complete:
            baseline = await self.session.scalar(
                select(BugZentaoSyncBaseline).where(
                    BugZentaoSyncBaseline.bug_id == bug_id,
                    BugZentaoSyncBaseline.field_group == "description",
                )
            )
            if baseline is None:
                # 本地摘要按应用后的正文计算，远端摘要按当前远端净化文本计算：
                # 两侧表示形式不同，基线记录"本轮确认时各自的样子"（R32）。
                self.session.add(
                    BugZentaoSyncBaseline(
                        bug_id=bug_id,
                        field_group="description",
                        local_snapshot_json={"digest": _digest(clean)},
                        remote_snapshot_json={
                            "digest": mapping.remote_description(steps)["digest"]
                        },
                        operation_id=operation_id,
                        applied_at=datetime.now(UTC),
                    )
                )
        self.session.add(
            BugActivity(
                activity_id=new_id(),
                bug_id=bug_id,
                kind="sync",
                actor_user_id=user_id,
                action="zentao_files",
                content=f"从禅道拉取文件：成功 {pulled_count} 个，待处理 {len(notes)} 个",
                detail_json={
                    "operationId": operation_id,
                    "remoteBugId": remote_bug_id,
                    "pulled": pulled_count,
                    "notes": notes,
                },
            )
        )
        await self.repository.commit()
        for note in notes:
            result["pending"].append({"field": "description", "reason": note})
        if complete and "description" in {item["field"] for item in result["pending"]}:
            result["pending"] = [
                item for item in result["pending"] if not item["field"] == "description"
            ]

    async def _pull_one(
        self,
        client,
        access,
        user_id: str,
        project_id: str,
        bug_id: str,
        remote_bug_id: int,
        remote_file_id: int,
        operation_id: str,
        meta: dict,
    ) -> tuple[str | None, str | None]:
        """单个远端文件：元数据核对 → 平台票据 → MCP 回传内容 → 校验入库。"""
        try:
            metadata = await client.call(
                "get_bug_attachment", {"bugId": remote_bug_id, "fileId": remote_file_id}
            )
            if metadata.get("status") != "success":
                raise McpCallError("禅道附件核对失败")
            filename = str(
                metadata.get("filename") or meta.get("title") or f"file-{remote_file_id}"
            )
            size = int(metadata.get("size") or 0)
            sha256 = str(metadata.get("sha256") or "")
            if size <= 0 or len(sha256) != 64:
                raise McpCallError("禅道附件元数据不完整")
            upload = await self.bugs.files.initiate_pull(
                user_id,
                project_id,
                bug_id=bug_id,
                filename=filename,
                size=size,
                sha256=sha256,
            )
            file_id = upload["fileId"]
        except (AppError, McpCallError) as exc:
            message = get_pull_error(exc)
            await self._record_pull(
                bug_id,
                "",
                access,
                remote_bug_id,
                remote_file_id,
                operation_id,
                user_id,
                "failed",
                message,
            )
            return None, message
        try:
            transfer = await client.call(
                "get_bug_attachment",
                {"bugId": remote_bug_id, "fileId": remote_file_id, "uploadUrl": upload["upload"]},
            )
            if transfer.get("status") != "success" or not transfer.get("uploaded"):
                raise McpCallError("禅道附件内容回传未完成")
            await self.bugs.files.complete(user_id, file_id)
            await self.bugs.files.attach(
                user_id, file_id, project_id, "bug", bug_id, purpose="attachment"
            )
        except (AppError, McpCallError) as exc:
            message = get_pull_error(exc)
            await self._record_pull(
                bug_id,
                file_id,
                access,
                remote_bug_id,
                remote_file_id,
                operation_id,
                user_id,
                "failed",
                message,
            )
            return None, message
        await self._record_pull(
            bug_id,
            file_id,
            access,
            remote_bug_id,
            remote_file_id,
            operation_id,
            user_id,
            "succeeded",
            "",
        )
        return file_id, None

    async def _record_pull(
        self,
        bug_id: str,
        file_id: str,
        access,
        remote_bug_id: int,
        remote_file_id: int,
        operation_id: str,
        user_id: str,
        status: str,
        message: str,
    ) -> None:
        if not file_id:
            # 尚无本地文件行的失败只进待处理清单，重试由反向拉取完成（R56）。
            return
        self.session.add(
            BugZentaoAttachment(
                bug_id=bug_id,
                file_id=file_id,
                sha256="",
                instance_url=access.base_url,
                remote_bug_id=remote_bug_id,
                remote_file_id=remote_file_id,
                operation_id=operation_id,
                direction="pull",
                actor_user_id=user_id,
                status=status,
                error_message=message,
            )
        )
        await self.repository.commit()

    async def _replay(self, operation_id: str) -> dict | None:
        """同一请求编号的重复提交返回原结果，不重复创建（R11/R56）。"""
        row = await self.session.scalar(
            select(BugZentaoPush).where(BugZentaoPush.operation_id == operation_id)
        )
        if row is None or row.source != "import":
            return None
        bug = await self.repository.get_bug(row.bug_id)
        if bug is None:
            return None
        return self._result(
            int(row.remote_bug_id or 0),
            "success",
            bug_id=bug.bug_id,
            bug_no=bug.bug_no,
            title=bug.title,
        )

    async def _create_rows(
        self,
        access,
        binding,
        user_id: str,
        project_id: str,
        operation_id: str,
        item: ZentaoBugImportItemRequest,
        snapshot: dict,
        status_fields: dict,
        description: dict,
        resolved: dict,
        pending: list[dict[str, str]],
    ) -> dict:
        instance_url = access.base_url
        target = {
            "mcpServiceId": access.service_id,
            "instanceUrl": instance_url,
            "project": int(binding.remote_resource_id),
        }
        bug = Bug(
            bug_id=new_id(),
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
            activity_id=new_id(),
            bug_id=bug.bug_id,
            kind=BugActivityKind.STATUS_CHANGE.value,
            actor_user_id=user_id,
            action="create",
            from_status="",
            to_status=bug.status,
        )
        sync_activity = BugActivity(
            activity_id=new_id(),
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
            service_id=access.service_id,
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
            return self._result(
                snapshot["remoteBugId"], "failed", error_message="Bug 编号分配冲突，请重试"
            )
        return self._result(
            snapshot["remoteBugId"],
            "success",
            bug_id=bug.bug_id,
            bug_no=bug.bug_no,
            title=bug.title,
            pending=pending,
        )

    async def _conflict_result(
        self, project_id: str, instance_url: str, remote_bug_id: int, title: str
    ) -> dict:
        """唯一约束兜底：区分本项目重复与其他项目占用（R12，不泄露去向）。"""
        link = await self.session.scalar(
            select(BugZentaoPush).where(
                BugZentaoPush.instance_key == instance_key(instance_url),
                BugZentaoPush.remote_bug_id == remote_bug_id,
            )
        )
        if link is not None:
            bug = await self.repository.get_bug(link.bug_id)
            if bug is not None and bug.project_id == project_id:
                return self._result(
                    remote_bug_id,
                    "already_linked",
                    bug_id=bug.bug_id,
                    bug_no=bug.bug_no,
                    title=bug.title,
                    error_message="该禅道 Bug 已导入过，请从现有平台 Bug 同步",
                )
        return self._result(
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

    @staticmethod
    def _result(
        remote_bug_id: int,
        status: str,
        *,
        bug_id: str = "",
        bug_no: int = 0,
        title: str = "",
        error_message: str = "",
        pending: list[dict[str, str]] | None = None,
    ) -> dict:
        return {
            "remote_bug_id": remote_bug_id,
            "status": status,
            "bug_id": bug_id,
            "bug_no": bug_no,
            "title": title,
            "error_message": error_message,
            "pending": pending or [],
        }

    async def _assignable(self, project_id: str, user_id: str) -> bool:
        return await assignable_member(self.repository, project_id, user_id)


async def duplicate_local_id(
    repository, project_id: str, instance_url: str, remote_bug_id: int
) -> int | None:
    """远端 duplicateBug 解析为同项目平台 Bug 主键；不可解析返回 None（Q04）。"""
    if not remote_bug_id:
        return None
    link = await repository.session.scalar(
        select(BugZentaoPush).where(
            BugZentaoPush.instance_key == instance_key(instance_url),
            BugZentaoPush.remote_bug_id == remote_bug_id,
        ),
    )
    if link is None:
        return None
    bug = await repository.get_bug(link.bug_id)
    if bug is None or bug.project_id != project_id:
        return None
    return bug.id


async def assignable_member(repository, project_id: str, user_id: str) -> bool:
    """项目所有者不是 project_members 行，因此单独判断。"""
    project = await repository.get_project(project_id)
    if project is None:
        return False
    if project.user_id == user_id:
        return True
    return await repository.get_project_member(project_id, user_id) is not None


_IMG_TAG = r"<img\b[^>]*/?>"
_FILE_REF = r"file-read-(\d+)"
_SRC_ATTR = r"\ssrc=(\"[^\"]*\"|'[^']*')"


def _search_file_ref(tag: str) -> int | None:
    match = _re_search(_FILE_REF, tag, _RE_I)
    return int(match.group(1)) if match else None


def _image_refs(raw_html: str) -> list[int]:
    """正文图片引用的禅道文件编号，按出现顺序去重（R44）。"""
    refs: list[int] = []
    for match in _re_finditer(_FILE_REF, raw_html or "", _RE_I):
        rid = int(match.group(1))
        if rid not in refs:
            refs.append(rid)
    return refs


def _attachment_index(raw: object) -> dict[int, dict]:
    """远端附件清单规范化为 {编号: {title, size}}；形状异常按空处理（R44）。"""
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list):
        return {}
    index: dict[int, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        if identifier is None:
            continue
        try:
            rid = int(identifier)
        except (TypeError, ValueError):
            continue
        if rid > 0:
            index[rid] = {"title": str(item.get("title") or ""), "size": item.get("size") or 0}
    return index


def _rewrite_images(raw_html: str, mapping: dict[int, str]) -> tuple[str, list[int]]:
    """把已解析图片的禅道地址改写为平台 data-file-id；未解析图片剔除并返回清单。"""
    resolved: list[int] = []

    def repl(match):
        tag = match.group(0)
        found = _re_search(_FILE_REF, tag, _RE_I)
        if found is None:
            return ""
        local = mapping.get(int(found.group(1)))
        if local is None:
            return ""
        resolved.append(int(found.group(1)))
        return _re_sub(_SRC_ATTR, f' data-file-id="{local}"', tag, count=1)

    return _re_sub(_IMG_TAG, repl, raw_html or "", flags=_RE_I), resolved


def _file_label(remote_file_id: int, meta: dict, message: str) -> str:
    title = meta.get("title") or f"#{remote_file_id}"
    return f"文件 {title}（#{remote_file_id}）待处理：{message}"


def get_pull_error(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return str(exc)


def _digest(text: str) -> str:
    return sha256((text or "").encode()).hexdigest()


def _optional_remote_id(value: object) -> int:
    try:
        if isinstance(value, bool) or value is None or str(value).strip() == "":
            return 0
        result = int(str(value).strip())
    except ValueError:
        return 0
    return result if result > 0 else 0
