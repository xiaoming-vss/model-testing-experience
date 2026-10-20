"""Authorize and coordinate remote reads, atomic Bug creation, then recoverable file pulls."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from testing_agent.services.bug import BugService
    from testing_agent.services.integration_connection import IntegrationConnectionService


from testing_agent.core.errors import AppError
from testing_agent.core.sid import new_id
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.zentao_bug_import import (
    execution_for_sprint,
    linked_remote_ids,
    project_binding,
)
from testing_agent.schemas.bug_zentao_import import (
    ZentaoBugCandidateItem,
    ZentaoBugImportItemRequest,
    ZentaoBugImportPreview,
    ZentaoBugImportResult,
)
from testing_agent.services.bug_import.contracts import (
    BugImportResult,
    BugImportTarget,
    PreparedBugImport,
    import_result,
)
from testing_agent.services.bug_import.files import BugImportFiles
from testing_agent.services.bug_import.prepare import BugImportPreparation
from testing_agent.services.bug_import.remote import (
    fetch_detail,
    optional_remote_id,
    paged_remote_bugs,
)
from testing_agent.services.bug_import.writer import BugImportWriter
from testing_agent.services.common import dump, paged_payload
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.project_access import require_project_id
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_mcp import ZentaoMcpAccess, ZentaoMcpConnection


class ZentaoBugImportService:
    def __init__(
        self,
        bugs: BugService,
        connections: IntegrationConnectionService,
        *,
        client_factory: Callable[[str, str], McpClient] | None = None,
    ) -> None:
        self.bugs = bugs
        self.repository = bugs.repository
        self.session = bugs.repository.session
        self.connections = connections
        self.client_factory = client_factory or McpClient

        self.preparation = BugImportPreparation(self.repository)
        self.writer = BugImportWriter(self.repository, id_factory=new_id)
        self.file_pull = BugImportFiles(self.repository, bugs.files, id_factory=new_id)

    async def _access(self, user_id: str, project_id: str):
        """写入权限 + 项目级禅道绑定 + 本人授权与实例核对（R07/R08/R15）。"""
        await require_project_id(self.session, user_id, project_id, "write")
        binding = await project_binding(self.session, project_id)
        if binding is None:
            raise AppError(400, "当前项目尚未绑定禅道项目，请先完成资源绑定", 400)
        access = await ZentaoMcpAccess(self.connections).resolve(
            user_id, project_id, expected_instance=binding.instance_url
        )
        return access, binding

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
        execution_id = await execution_for_sprint(
            self.repository, project_id, instance_key(access.base_url), sprint_id
        )
        if sprint_id and not execution_id:
            raise AppError(400, "当前迭代未绑定禅道执行，请先在资源绑定中完成迭代绑定", 400)
        try:
            async with self.client_factory(access.endpoint, access.token) as client:
                if execution_id:
                    rows = await paged_remote_bugs(
                        client,
                        "get_executions_executionID_bugs",
                        {"executionID": execution_id},
                    )
                    scope = "execution"
                else:
                    rows = await paged_remote_bugs(
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
        linked = await linked_remote_ids(
            self.session, instance_key(access.base_url), [int(row["id"]) for row in matched]
        )
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
                        "execution": optional_remote_id(row.get("execution")),
                        "story": optional_remote_id(row.get("story")),
                        "linked": int(row["id"]) in linked,
                    },
                )
            )
        return {
            "scope": scope,
            "executionId": execution_id or None,
            **paged_payload(items, len(matched)),
        }

    async def preview(self, user_id: str, project_id: str, remote_bug_ids: list[int]) -> dict:
        access, _ = await self._access(user_id, project_id)
        results: list[dict] = []
        try:
            async with self.client_factory(access.endpoint, access.token) as client:
                for remote_bug_id in dict.fromkeys(remote_bug_ids):
                    results.append(
                        await self.preparation.preview(
                            await fetch_detail(client, remote_bug_id),
                            access,
                            project_id,
                            remote_bug_id,
                        )
                    )
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc
        return {"items": [dump(ZentaoBugImportPreview, item) for item in results]}

    async def import_bugs(
        self,
        user_id: str,
        project_id: str,
        request_id: str,
        items: list[ZentaoBugImportItemRequest],
    ) -> dict:
        access, binding = await self._access(user_id, project_id)
        results: list[BugImportResult] = []
        seen: set[int] = set()
        try:
            async with self.client_factory(access.endpoint, access.token) as client:
                for item in items:
                    if item.remote_bug_id in seen:
                        results.append(
                            import_result(
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
        client: McpClient,
        access: ZentaoMcpConnection,
        binding: ResourceBinding,
        user_id: str,
        project_id: str,
        request_id: str,
        item: ZentaoBugImportItemRequest,
    ) -> BugImportResult:
        operation_id = f"{request_id}:{item.remote_bug_id}"
        replayed = await self.writer.replay(operation_id)
        if replayed is not None:
            return replayed
        detail = await fetch_detail(client, item.remote_bug_id)
        prepared = await self.preparation.prepare(detail, access, project_id, item)
        if not isinstance(prepared, PreparedBugImport):
            return prepared
        created = await self.writer.create(
            BugImportTarget(
                user_id=user_id,
                project_id=project_id,
                operation_id=operation_id,
                instance_url=access.base_url,
                service_id=access.service_id,
                remote_project_id=int(binding.remote_resource_id),
            ),
            prepared,
        )
        if created["status"] != "success":
            return created
        # R44-R47：正文与附件在本地创建事务之后拉取（外部等待在长事务之外），
        # 单文件失败只记待处理，不影响已创建的 Bug，可随反向拉取补齐。
        await self.file_pull.pull(
            client,
            access,
            user_id,
            project_id,
            created["bug_id"],
            int(prepared.snapshot["remoteBugId"]),
            detail,
            operation_id,
            created,
        )
        return created
