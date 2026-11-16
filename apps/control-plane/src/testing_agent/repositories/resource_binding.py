from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from sqlalchemy import RowMapping, select

from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.base import ResourceRepository

# 激活的 GitLab 仓库绑定(需求代码绑定)通用过滤条件。
_GITLAB_ACTIVE_REPO_BINDING_CRITERIA = (
    ResourceBinding.provider == "gitlab",
    ResourceBinding.remote_resource_type == "repository",
    ResourceBinding.status == "active",
)


class RepoBindingWithSprint(NamedTuple):
    """需求代码绑定与其所属迭代(基线解析历史行)。"""

    binding: ResourceBinding
    sprint: Sprint


class ResourceBindingRepository(ResourceRepository):
    model = ResourceBinding
    id_column = "binding_id"

    async def list_zentao_summaries(
        self, resource_type: str, resource_ids: Sequence[str]
    ) -> Sequence[RowMapping]:
        if not resource_ids:
            return []
        result = await self.session.execute(
            select(
                ResourceBinding.local_resource_id,
                ResourceBinding.binding_id,
                ResourceBinding.provider,
                ResourceBinding.remote_resource_id,
                ResourceBinding.remote_name_snapshot,
                ResourceBinding.status,
            )
            .where(
                ResourceBinding.local_resource_type == resource_type,
                ResourceBinding.local_resource_id.in_(resource_ids),
                ResourceBinding.provider == "zentao",
                ResourceBinding.status == "active",
            )
            .order_by(ResourceBinding.created_at.desc(), ResourceBinding.id.desc())
        )
        return result.mappings().all()

    async def list_code_summaries(self, resource_ids: Sequence[str]) -> Sequence[RowMapping]:
        if not resource_ids:
            return []
        result = await self.session.execute(
            select(
                ResourceBinding.local_resource_id,
                ResourceBinding.remote_resource_id,
                ResourceBinding.remote_name_snapshot,
                ResourceBinding.extra_json,
            )
            .where(
                *_GITLAB_ACTIVE_REPO_BINDING_CRITERIA,
                ResourceBinding.local_resource_type == "requirement",
                ResourceBinding.local_resource_id.in_(resource_ids),
            )
            .order_by(ResourceBinding.id)
        )
        return result.mappings().all()

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_project_for_update(self, project_id: str) -> Project | None:
        return await self.session.scalar(
            select(Project)
            .where(Project.project_id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def get_sprint_for_update(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(
            select(Sprint)
            .where(Sprint.sprint_id == sprint_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_requirement(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(Requirement.requirement_id == requirement_id)
        )

    async def get_requirement_for_update(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement)
            .where(Requirement.requirement_id == requirement_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_active_by_local_resource(
        self,
        resource_type: str,
        resource_id: str,
    ) -> ResourceBinding | None:
        return await self.session.scalar(
            select(ResourceBinding)
            .where(
                ResourceBinding.local_resource_type == resource_type,
                ResourceBinding.local_resource_id == resource_id,
                ResourceBinding.provider == "zentao",
                ResourceBinding.status == "active",
            )
            .order_by(ResourceBinding.id.asc())
            .limit(1)
        )

    async def exists_active_by_remote_resource(
        self,
        provider: str,
        connection_id: str,
        remote_resource_type: str,
        remote_resource_id: str,
        *,
        instance: str | None = None,
    ) -> bool:
        row = await self.session.scalar(
            select(ResourceBinding.binding_id)
            .where(
                ResourceBinding.provider == provider,
                (
                    ResourceBinding.instance_key == instance
                    if instance is not None
                    else ResourceBinding.connection_id == connection_id
                ),
                ResourceBinding.remote_resource_type == remote_resource_type,
                ResourceBinding.remote_resource_id == remote_resource_id,
                ResourceBinding.status == "active",
            )
            .limit(1)
        )
        return row is not None

    async def list(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> list[ResourceBinding]:
        return list(
            (
                await self.session.scalars(
                    select(ResourceBinding)
                    .where(
                        ResourceBinding.local_resource_type == resource_type,
                        ResourceBinding.local_resource_id == resource_id,
                    )
                    .order_by(ResourceBinding.created_at.desc())
                )
            ).all()
        )

    async def list_project_bindings(
        self, user_id: str, project_id: str
    ) -> Sequence[ResourceBinding]:
        """项目绑定列表:仅返回禅道绑定;GitLab 群组绑定已移除。"""
        return list(
            (
                await self.session.scalars(
                    select(ResourceBinding)
                    .where(
                        ResourceBinding.local_resource_type == "project",
                        ResourceBinding.local_resource_id == project_id,
                        ResourceBinding.provider == "zentao",
                    )
                    .order_by(ResourceBinding.created_at.desc())
                )
            ).all()
        )

    async def list_requirement_bindings(
        self, user_id: str, requirement_id: str
    ) -> Sequence[ResourceBinding]:
        """需求代码绑定列表:gitlab 仓库绑定是项目级共享资产,不过滤 user_id(ADR-0007);
        禅道绑定遵循相同项目权限。"""
        return list(
            (
                await self.session.scalars(
                    select(ResourceBinding)
                    .where(
                        ResourceBinding.local_resource_type == "requirement",
                        ResourceBinding.local_resource_id == requirement_id,
                    )
                    .order_by(ResourceBinding.created_at.desc())
                )
            ).all()
        )

    async def exists_active_requirement_repo_binding(
        self,
        requirement_id: str,
        repository_id: str,
        *,
        instance: str | None = None,
    ) -> bool:
        row = await self.session.scalar(
            select(ResourceBinding.binding_id)
            .where(
                *_GITLAB_ACTIVE_REPO_BINDING_CRITERIA,
                ResourceBinding.local_resource_type == "requirement",
                ResourceBinding.local_resource_id == requirement_id,
                ResourceBinding.remote_resource_id == repository_id,
                *((ResourceBinding.instance_key == instance,) if instance is not None else ()),
            )
            .limit(1)
        )
        return row is not None

    async def list_active_repo_bindings_for_requirement(
        self, requirement_id: str
    ) -> Sequence[ResourceBinding]:
        """需求激活的 GitLab 仓库绑定(共享资产,不过滤 user_id,ADR-0007)。"""
        return list(
            (
                await self.session.scalars(
                    select(ResourceBinding)
                    .where(
                        *_GITLAB_ACTIVE_REPO_BINDING_CRITERIA,
                        ResourceBinding.local_resource_type == "requirement",
                        ResourceBinding.local_resource_id == requirement_id,
                    )
                    .order_by(ResourceBinding.id.asc())
                )
            ).all()
        )

    async def list_active_repo_bindings_for_sprint(
        self, sprint_id: str
    ) -> Sequence[ResourceBinding]:
        """迭代内所有激活的 GitLab 需求代码绑定(仓库),供迭代代码概览聚合。

        覆盖该迭代全部需求(需求与迭代均未删除),不过滤 user_id(ADR-0007);
        按绑定创建时间倒序,创建时间相同时取 id 较大者在前,保证聚合结果确定。
        """
        return list(
            (
                await self.session.scalars(
                    select(ResourceBinding)
                    .join(
                        Requirement,
                        Requirement.requirement_id == ResourceBinding.local_resource_id,
                    )
                    .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
                    .where(
                        *_GITLAB_ACTIVE_REPO_BINDING_CRITERIA,
                        ResourceBinding.local_resource_type == "requirement",
                        Sprint.sprint_id == sprint_id,
                    )
                    .order_by(ResourceBinding.created_at.desc(), ResourceBinding.id.desc())
                )
            ).all()
        )

    async def list_active_repo_bindings_with_sprint_for_project(
        self, project_id: str
    ) -> Sequence[RepoBindingWithSprint]:
        """项目内激活的 GitLab 需求代码绑定(仓库)及其所属迭代:
        基线解析历史口径,需求与迭代均未删除,不过滤 user_id(ADR-0007)。"""
        rows = await self.session.execute(
            select(ResourceBinding, Sprint)
            .join(Requirement, Requirement.requirement_id == ResourceBinding.local_resource_id)
            .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
            .where(
                *_GITLAB_ACTIVE_REPO_BINDING_CRITERIA,
                ResourceBinding.local_resource_type == "requirement",
                Sprint.project_id == project_id,
            )
            .order_by(ResourceBinding.created_at.desc(), ResourceBinding.id.desc())
        )
        return [RepoBindingWithSprint(binding, sprint) for binding, sprint in rows.all()]

    async def get(
        self, resource_type: str, resource_id: str, binding_id: str
    ) -> ResourceBinding | None:
        return await self.session.scalar(
            select(ResourceBinding).where(
                ResourceBinding.binding_id == binding_id,
                ResourceBinding.local_resource_type == resource_type,
                ResourceBinding.local_resource_id == resource_id,
            )
        )

    def add(self, binding: ResourceBinding) -> None:
        self.session.add(binding)

    async def refresh(self, binding: ResourceBinding) -> None:
        await self.session.refresh(binding)
