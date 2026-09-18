"""基线解析服务(工单 05,RC-3)。

对需求代码绑定的每个仓库独立解析基线分支,五种情形:

① 手工设置 baseline_branch → 直接使用,不查历史;
② 未设置 → 在当前迭代之前的所有迭代中查找该仓库最近一次绑定的分支
   (迭代按结束时间排序,空则按创建时间);
③ 该仓库从未被绑定 → 无基线(视为全新变更);
④ 查找失败(分支已删等)→ 结构化错误并提示手工指定;
⑤ 命中迭代内存在多条绑定 → 取绑定记录创建时间最新的一条并标注。

查找范围严格限于之前迭代;本迭代内其他需求的绑定不作基线。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple

from testing_agent.core.errors import ErrNotFound
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.resource_binding import (
    RepoBindingWithSprint,
    ResourceBindingRepository,
)
from testing_agent.repositories.sprint import SprintRepository
from testing_agent.services.zentao_resource import truncate_error

# 远程分支存在性检查器;未提供时不校验远端(纯逻辑模式,便于单测)。
# 接入 GitLab 后传入实现:校验基线分支是否仍存在(工单 06 构建任务快照时接线)。
BranchExistsChecker = Callable[[str, str], Awaitable[bool]]

MULTI_BINDING_NOTE = "发现多条绑定,已取最近一条"


@dataclass(frozen=True, slots=True)
class RepoBaselineResolution:
    """单仓库基线解析结果:仓库标识、分支、基线 ref 或 none、失败原因。"""

    repository_id: str
    branch: str
    baseline_ref: str | None = None
    note: str = ""
    error: str = ""

    def dump(self) -> dict[str, Any]:
        return {
            "repositoryId": self.repository_id,
            "branch": self.branch,
            "baselineRef": self.baseline_ref,
            "note": self.note,
            "error": self.error,
        }


class BindingResolution(NamedTuple):
    """绑定与其基线解析结果(迭代级解析的逐绑定行,工单 08)。"""

    binding: ResourceBinding
    resolution: RepoBaselineResolution


def sprint_sort_key(sprint: Sprint) -> tuple[datetime, datetime]:
    """迭代时间线排序键:按结束时间;未结束(空)则按创建时间(工单 05 口径)。

    次键为创建时间,与「之前迭代」的过滤口径保持一致:结束时间相同的
    兄弟迭代按创建时间分先后。
    """
    return (
        sprint.end_time if sprint.end_time is not None else sprint.created_at,
        sprint.created_at,
    )


def binding_sort_key(binding: ResourceBinding) -> tuple[datetime, int]:
    """绑定排序键:创建时间最新在前;创建时间相同时取 id 较大者,保证结果确定。"""
    return (binding.created_at or datetime.min, getattr(binding, "id", 0) or 0)


class BaselineResolutionService:
    def __init__(
        self,
        binding_repository: ResourceBindingRepository,
        sprint_repository: SprintRepository,
        branch_exists: BranchExistsChecker | None = None,
    ):
        self.binding_repository = binding_repository
        self.sprint_repository = sprint_repository
        self.branch_exists = branch_exists

    async def resolve_for_requirement(
        self,
        requirement_id: str,
        branch_exists: BranchExistsChecker | None = None,
    ) -> list[RepoBaselineResolution]:
        """解析需求各绑定仓库的基线。

        branch_exists 按次覆盖构造时注入的检查器(工单 06 构建任务快照时
        按仓库连接接线);传 None 则沿用构造时配置。
        """
        return [
            row.resolution
            for row in await self.resolve_requirement_bindings(requirement_id, branch_exists)
        ]

    async def resolve_requirement_bindings(
        self, requirement_id: str, branch_exists: BranchExistsChecker | None = None
    ) -> list[BindingResolution]:
        checker = branch_exists if branch_exists is not None else self.branch_exists
        requirement = await self.binding_repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound
        current_sprint = await self.binding_repository.get_sprint(requirement.sprint_id)
        if current_sprint is None:
            raise ErrNotFound

        bindings = await self.binding_repository.list_active_repo_bindings_for_requirement(
            requirement_id
        )
        return [
            BindingResolution(binding, resolution)
            for binding, resolution in await self._resolve_bindings(
                current_sprint.project_id, current_sprint, bindings, checker
            )
        ]

    async def resolve_for_sprint(self, sprint_id: str) -> list[BindingResolution]:
        """解析迭代内全部需求代码绑定的基线(工单 08 迭代代码概览复用口径)。

        规则与 resolve_for_requirement 一致,区别仅两点:一次解析整迭代的
        绑定(迭代时间线与项目历史只查询一次);不做情形④的远端分支存在
        性校验——概览为展示场景,基线分支失效会在后续 compare 调用中暴露
        并标注在该仓库条目上。返回按绑定创建时间倒序(最新在前)。
        """
        sprint = await self.binding_repository.get_sprint(sprint_id)
        if sprint is None:
            raise ErrNotFound
        bindings = list(
            await self.binding_repository.list_active_repo_bindings_for_sprint(sprint_id)
        )
        return [
            BindingResolution(binding, resolution)
            for binding, resolution in await self._resolve_bindings(
                sprint.project_id, sprint, bindings, None
            )
        ]

    async def _resolve_bindings(
        self,
        project_id: str,
        sprint: Sprint,
        bindings: Sequence[ResourceBinding],
        branch_exists: BranchExistsChecker | None,
    ) -> list[tuple[ResourceBinding, RepoBaselineResolution]]:
        """逐绑定解析基线,resolve_for_requirement 与 resolve_for_sprint 的共享核心。

        全部为手工基线(情形①)时不查历史;否则迭代时间线与项目历史各只
        查询一次,再按绑定逐个解析。
        """
        if not bindings:
            return []
        if not self._needs_history(bindings):
            # 情形①:全部为手工基线,直接使用,不查历史。
            return [(binding, self._resolve_manual(binding)) for binding in bindings]
        sprints = await self.sprint_repository.list_active_by_project(project_id)
        previous_sprints = self._previous_sprints(sprints, sprint)
        history = await self.binding_repository.list_active_repo_bindings_with_sprint_for_project(
            project_id
        )
        return [
            (
                binding,
                await self._resolve_repo(binding, previous_sprints, history, branch_exists),
            )
            for binding in bindings
        ]

    @staticmethod
    def _needs_history(bindings: Sequence[ResourceBinding]) -> bool:
        return any(
            not str((binding.extra_json or {}).get("baseline_branch") or "").strip()
            for binding in bindings
        )

    @staticmethod
    def _branches_of(binding: ResourceBinding) -> tuple[str, str]:
        """绑定的 (分支, 基线分支),均为去空白后的字符串。"""
        extra = binding.extra_json or {}
        branch = str(extra.get("branch") or "").strip()
        baseline_branch = str(extra.get("baseline_branch") or "").strip()
        return branch, baseline_branch

    @staticmethod
    def _resolve_manual(binding: ResourceBinding) -> RepoBaselineResolution:
        repository_id = binding.remote_resource_id
        branch, baseline_branch = BaselineResolutionService._branches_of(binding)
        if not branch:
            return RepoBaselineResolution(
                repository_id, "", error="绑定缺少分支信息,请手工指定基线分支"
            )
        return RepoBaselineResolution(repository_id, branch, baseline_ref=baseline_branch)

    @staticmethod
    def _previous_sprints(sprints: Sequence[Sprint], current_sprint: Sprint) -> list[Sprint]:
        """当前迭代之前的所有迭代,按时间线倒序(最近在前)。

        之前 = 时间线排序键严格小于当前迭代;本迭代与之后迭代不参与历史。
        """
        current_key = sprint_sort_key(current_sprint)
        previous = [
            sprint
            for sprint in sprints
            if sprint.sprint_id != current_sprint.sprint_id
            and sprint_sort_key(sprint) < current_key
        ]
        previous.sort(key=sprint_sort_key, reverse=True)
        return previous

    async def _resolve_repo(
        self,
        binding: ResourceBinding,
        previous_sprints: Sequence[Sprint],
        history: Sequence[RepoBindingWithSprint],
        branch_exists: BranchExistsChecker | None,
    ) -> RepoBaselineResolution:
        repository_id = binding.remote_resource_id
        branch, baseline_branch = self._branches_of(binding)
        if not branch:
            return RepoBaselineResolution(
                repository_id, "", error="绑定缺少分支信息,请手工指定基线分支"
            )
        if baseline_branch:
            # 情形①:手工基线直接使用,不查历史、不校验远端。
            return RepoBaselineResolution(repository_id, branch, baseline_ref=baseline_branch)

        # 情形②⑤:自动查找,按时间线倒序遍历之前迭代,命中第一个含该仓库绑定的迭代。
        for sprint in previous_sprints:
            candidates = [
                row.binding
                for row in history
                if row.sprint.sprint_id == sprint.sprint_id
                and row.binding.remote_resource_id == repository_id
                and getattr(row.binding, "instance_key", "") == getattr(binding, "instance_key", "")
            ]
            if candidates:
                return await self._resolve_from_candidates(
                    repository_id, branch, candidates, branch_exists
                )
        # 情形③:该仓库从未被绑定 → 无基线。
        return RepoBaselineResolution(repository_id, branch)

    async def _resolve_from_candidates(
        self,
        repository_id: str,
        branch: str,
        candidates: Sequence[ResourceBinding],
        branch_exists: BranchExistsChecker | None,
    ) -> RepoBaselineResolution:
        ordered = sorted(candidates, key=binding_sort_key, reverse=True)
        latest = ordered[0]
        note = MULTI_BINDING_NOTE if len(ordered) > 1 else ""
        baseline_branch, _ = self._branches_of(latest)
        if not baseline_branch:
            return RepoBaselineResolution(
                repository_id,
                branch,
                error="该仓库最近一次绑定缺少分支信息,请手工指定基线分支",
            )
        if branch_exists is None:
            return RepoBaselineResolution(
                repository_id, branch, baseline_ref=baseline_branch, note=note
            )
        # 情形④:基线分支已删除、远端查询失败等 → 结构化错误提示手工指定。
        try:
            exists = await branch_exists(repository_id, baseline_branch)
        except Exception as exc:
            return RepoBaselineResolution(
                repository_id,
                branch,
                error=f"基线分支查找失败,请手工指定基线分支({truncate_error(str(exc))})",
            )
        if not exists:
            return RepoBaselineResolution(
                repository_id,
                branch,
                error=f"基线分支 {baseline_branch} 已不存在,请手工指定基线分支",
            )
        return RepoBaselineResolution(
            repository_id, branch, baseline_ref=baseline_branch, note=note
        )
