"""迭代代码变更概览(工单 08,RC-6)。

聚合迭代内所有需求代码绑定为按仓库去重的变更概览:

- 聚合键为 (仓库, 分支) 对比单元,同一对比单元只出现一次(取创建时间
  最新的绑定,与 RC-3 多条绑定口径一致);基线解析复用 RC-3 服务
  (resolve_for_sprint,迭代时间线与项目历史只查询一次);
- 有基线:调 GitLab compare API 统计 commits 数与增删行数;
- 无基线(该仓库从未在之前迭代绑定):以 git 空树 SHA 为 from 对比并标记
  「新增仓库」(GitLab 无 empty_tree 参数,需显式传空树 SHA);
- 概览为展示场景,不同于分析任务的 fail-fast:单仓库失败(凭据缺失、
  compare 失败)仅标注该仓库错误与补救建议,不影响其余仓库与整体返回;
  无任何绑定时返回空态结构;
- 实时结果按当前用户授权读取，不跨请求复用缓存。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from testing_agent.core.errors import AppError
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.services.baseline_resolution import (
    BaselineResolutionService,
    RepoBaselineResolution,
)
from testing_agent.services.gitlab_resource import GitLabResourceError
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.repo_gitlab_access import resolve_repo_gitlab_access
from testing_agent.services.sprint import SprintService
from testing_agent.services.zentao_resource import truncate_error

# git 空树 SHA:无基线仓库与空树对比,标记「新增仓库」(工单 08)。
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

COMPARE_ERROR_REMEDIATION = "请检查 GitLab 连接有效性、分支是否存在,或手工指定基线分支后重试"
RESOLUTION_ERROR_REMEDIATION = "请修正绑定或手工指定基线分支后重试"
CONNECTION_UNRESOLVED_ERROR = "未解析到该仓库的 GitLab 凭据连接(群组绑定缺失或连接不可用)"
CONNECTION_UNRESOLVED_REMEDIATION = "请配置本人同实例 GitLab 授权；若有多个连接，请明确选择"


def dump_repository_entry(
    binding: ResourceBinding, resolution: RepoBaselineResolution
) -> dict[str, Any]:
    """绑定 + 基线解析 → 概览仓库条目骨架(统计字段由 compare 填充)。"""
    return {
        "repositoryId": str(binding.remote_resource_id or ""),
        "instanceUrl": binding.instance_url,
        "name": str(getattr(binding, "remote_name_snapshot", "") or ""),
        "groupId": str(binding.remote_parent_id or ""),
        "branch": resolution.branch,
        "baselineRef": resolution.baseline_ref,
        "baselineNote": resolution.note,
        "isNewRepository": resolution.baseline_ref is None and not resolution.error,
        "commitsCount": 0,
        "additions": 0,
        "deletions": 0,
        "error": resolution.error,
        "remediation": "",
    }


class SprintCodeOverviewService:
    def __init__(
        self,
        sprint_service: SprintService,
        binding_repository: ResourceBindingRepository,
        baseline_resolution_service: BaselineResolutionService,
        integration_connection_service: IntegrationConnectionService,
        credential_cipher: IntegrationCredentialCipher,
    ):
        self.sprint_service = sprint_service
        self.binding_repository = binding_repository
        self.baseline_resolution_service = baseline_resolution_service
        self.integration_connection_service = integration_connection_service
        self.credential_cipher = credential_cipher

    async def get_overview(
        self, user_id: str, sprint_id: str, connection_ids: dict[str, str] | None = None
    ) -> dict[str, Any]:
        sprint = await self.sprint_service.get_accessible_entity(user_id, sprint_id)
        # Always verify live access; a project-level cache cannot represent personal grants.
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for binding, resolution in await self.baseline_resolution_service.resolve_for_sprint(
            sprint_id
        ):
            key = (binding.instance_key, str(binding.remote_resource_id or ""), resolution.branch)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                await self._entry(
                    sprint.project_id,
                    binding,
                    resolution,
                    user_id,
                    (connection_ids or {}).get(binding.instance_url, ""),
                )
            )
        payload: dict[str, Any] = {
            "sprintId": sprint.sprint_id,
            "projectId": sprint.project_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "repositories": rows,
        }
        return payload

    async def _entry(
        self,
        project_id: str,
        binding: ResourceBinding,
        resolution: RepoBaselineResolution,
        user_id: str,
        connection_id: str = "",
    ) -> dict[str, Any]:
        entry = dump_repository_entry(binding, resolution)
        repository_id = entry["repositoryId"]
        if entry["error"]:
            entry["remediation"] = RESOLUTION_ERROR_REMEDIATION
            return entry
        try:
            access = await resolve_repo_gitlab_access(
                self.binding_repository,
                self.integration_connection_service,
                self.credential_cipher,
                project_id,
                binding,
                user_id=user_id,
                connection_id=connection_id,
            )
        except (AppError, ValueError):
            entry["error"] = CONNECTION_UNRESOLVED_ERROR
            entry["remediation"] = CONNECTION_UNRESOLVED_REMEDIATION
            return entry
        # 无基线仓库以空树 SHA 为 from(GitLab 无 empty_tree 参数,工单 08)。
        from_ref = entry["baselineRef"] or EMPTY_TREE_SHA
        try:
            client = self.integration_connection_service.gitlab_resource_client
            stats = await client.compare_repository_branches(
                access.base_url,
                access.access_token,
                repository_id,
                from_ref=from_ref,
                to_ref=entry["branch"],
            )
        except GitLabResourceError as exc:
            entry["error"] = truncate_error(str(exc))
            entry["remediation"] = COMPARE_ERROR_REMEDIATION
            return entry
        entry.update(stats)
        return entry
