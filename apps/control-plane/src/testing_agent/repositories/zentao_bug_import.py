from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.bug import BugRepository


async def project_binding(session: AsyncSession, project_id: str) -> ResourceBinding | None:
    return await session.scalar(
        select(ResourceBinding).where(
            ResourceBinding.provider == "zentao",
            ResourceBinding.status == "active",
            ResourceBinding.local_resource_type == "project",
            ResourceBinding.local_resource_id == project_id,
        )
    )


async def import_by_operation(session: AsyncSession, operation_id: str) -> BugZentaoPush | None:
    return await session.scalar(
        select(BugZentaoPush).where(BugZentaoPush.operation_id == operation_id)
    )


async def remote_link(
    session: AsyncSession, instance: str, remote_bug_id: int
) -> BugZentaoPush | None:
    return await session.scalar(
        select(BugZentaoPush).where(
            BugZentaoPush.instance_key == instance,
            BugZentaoPush.remote_bug_id == remote_bug_id,
        )
    )


async def duplicate_local_id(
    repository: BugRepository, project_id: str, instance: str, remote_bug_id: int
) -> int | None:
    """远端 duplicateBug 解析为同项目平台 Bug 主键；不可解析返回 None（Q04）。"""
    if not remote_bug_id:
        return None
    link = await remote_link(repository.session, instance, remote_bug_id)
    if link is None:
        return None
    bug = await repository.get_bug(link.bug_id)
    if bug is None or bug.project_id != project_id:
        return None
    return bug.id


async def assignable_member(repository: BugRepository, project_id: str, user_id: str) -> bool:
    """项目所有者不是 project_members 行，因此单独判断。"""
    project = await repository.get_project(project_id)
    if project is None:
        return False
    if project.user_id == user_id:
        return True
    return await repository.get_project_member(project_id, user_id) is not None


async def linked_remote_ids(
    session: AsyncSession, instance: str, remote_ids: list[int]
) -> set[int]:
    if not remote_ids:
        return set()
    rows = await session.scalars(
        select(BugZentaoPush.remote_bug_id).where(
            BugZentaoPush.instance_key == instance,
            BugZentaoPush.remote_bug_id.in_(remote_ids),
        )
    )
    return {int(value) for value in rows if value is not None}


async def find_binding(
    session: AsyncSession, local_type: str, remote_type: str, remote_id: str, instance: str
) -> ResourceBinding | None:
    row = await session.scalar(
        select(ResourceBinding).where(
            ResourceBinding.provider == "zentao",
            ResourceBinding.status == "active",
            ResourceBinding.local_resource_type == local_type,
            ResourceBinding.remote_resource_type == remote_type,
            ResourceBinding.remote_resource_id == remote_id,
            ResourceBinding.instance_key == instance,
        )
    )
    return row


async def execution_for_sprint(
    repository: BugRepository, project_id: str, instance: str, sprint_id: str
) -> int:
    """当前迭代绑定的禅道执行编号；未绑定返回 0（回退项目范围）。"""
    if not sprint_id:
        return 0
    sprint = await repository.get_sprint(sprint_id)
    if sprint is None or sprint.project_id != project_id:
        return 0
    binding = await repository.session.scalar(
        select(ResourceBinding).where(
            ResourceBinding.provider == "zentao",
            ResourceBinding.status == "active",
            ResourceBinding.local_resource_type == "sprint",
            ResourceBinding.local_resource_id == sprint_id,
            ResourceBinding.remote_resource_type == "execution",
            ResourceBinding.instance_key == instance,
        )
    )
    return int(binding.remote_resource_id) if binding else 0
