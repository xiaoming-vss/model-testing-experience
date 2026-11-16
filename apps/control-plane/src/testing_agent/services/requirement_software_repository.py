from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrNotFound,
    ErrRequirementSoftwareRepositoryBranchRequired,
    ErrRequirementSoftwareRepositoryConflict,
    dynamic_error,
)
from testing_agent.models.requirement_software_repository import (
    RequirementSoftwareRepository,
)
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.repositories.requirement_software_repository import (
    RequirementRepositoryBinding,
    RequirementSoftwareRepositoryRepository,
)
from testing_agent.repositories.software_repository import SoftwareRepositoryRepository
from testing_agent.schemas.requirement_software_repository import (
    RequirementSoftwareRepositoryCreateRequest,
    RequirementSoftwareRepositoryResponse,
    RequirementSoftwareRepositoryUpdateRequest,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.project_access import (
    ProjectAction,
    require_project_access,
)


def dump_requirement_software_repository(
    binding: RequirementRepositoryBinding,
) -> dict[str, Any]:
    association = binding.association
    repository = binding.software_repository
    git_repository = None
    if repository.repository_project_id:
        git_repository = {
            "project_id": repository.repository_project_id,
            "path": repository.repository_path,
            "name": repository.repository_name,
            "instance_url": repository.repository_instance_url,
        }
    data = {
        "requirement_id": association.requirement_id,
        "software_repository_id": association.software_repository_id,
        "software_repository_name": repository.name,
        "base_path": repository.base_path,
        "repository": git_repository,
        "branch": association.branch,
        "baseline_branch": association.baseline_branch,
        "created_by_user_id": association.created_by_user_id,
        "created_at": association.created_at,
        "updated_at": association.updated_at,
    }
    return RequirementSoftwareRepositoryResponse.model_validate(data).model_dump(
        by_alias=True, mode="json"
    )


class RequirementSoftwareRepositoryService:
    def __init__(
        self,
        repository: RequirementSoftwareRepositoryRepository,
        software_repositories: SoftwareRepositoryRepository,
        connections: IntegrationConnectionService | None = None,
    ) -> None:
        self.repository = repository
        self.software_repositories = software_repositories
        self.connections = connections

    async def list(self, user_id: str, requirement_id: str) -> dict[str, Any]:
        await self._scope(user_id, requirement_id, action="read")
        bindings = await self.repository.list_for_requirement_with_repository(requirement_id)
        return {
            "items": [dump_requirement_software_repository(binding) for binding in bindings],
            "total": len(bindings),
        }

    async def create(
        self,
        user_id: str,
        requirement_id: str,
        body: RequirementSoftwareRepositoryCreateRequest,
    ) -> dict[str, Any]:
        _requirement, project_id = await self._scope(user_id, requirement_id, action="write")
        repository = await self._software_repository(project_id, body.software_repository_id)
        await self._validate_branches(
            user_id,
            project_id,
            repository,
            branch=body.branch,
            baseline_branch=body.baseline_branch,
            require_both=True,
        )
        if await self.repository.get(requirement_id, repository.software_repository_id) is not None:
            raise ErrRequirementSoftwareRepositoryConflict()
        association = RequirementSoftwareRepository(
            requirement_id=requirement_id,
            software_repository_id=repository.software_repository_id,
            branch=body.branch,
            baseline_branch=body.baseline_branch,
            created_by_user_id=user_id,
        )
        self.repository.add(association)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ErrRequirementSoftwareRepositoryConflict() from exc
        await self.repository.refresh(association)
        return dump_requirement_software_repository(
            RequirementRepositoryBinding(association=association, software_repository=repository)
        )

    async def update(
        self,
        user_id: str,
        requirement_id: str,
        software_repository_id: str,
        body: RequirementSoftwareRepositoryUpdateRequest,
    ) -> dict[str, Any]:
        _requirement, project_id = await self._scope(user_id, requirement_id, action="write")
        association = await self.repository.get_for_update(requirement_id, software_repository_id)
        if association is None:
            raise ErrNotFound()
        repository = await self._software_repository(project_id, software_repository_id)
        branch = body.branch if body.branch is not None else association.branch
        baseline_branch = (
            body.baseline_branch
            if body.baseline_branch is not None
            else association.baseline_branch
        )
        # 换绑会清空分支，允许一次补一个分支，避免两个空值互相等待；提供值仍按仓库校验。
        await self._validate_branches(
            user_id,
            project_id,
            repository,
            branch=branch,
            baseline_branch=baseline_branch,
            require_both=False,
        )
        changed = False
        if branch != association.branch:
            association.branch = branch
            changed = True
        if baseline_branch != association.baseline_branch:
            association.baseline_branch = baseline_branch
            changed = True
        if changed:
            await self.repository.commit()
            await self.repository.refresh(association)
        return dump_requirement_software_repository(
            RequirementRepositoryBinding(association=association, software_repository=repository)
        )

    async def delete(
        self, user_id: str, requirement_id: str, software_repository_id: str
    ) -> dict[str, Any]:
        await self._scope(user_id, requirement_id, action="write")
        association = await self.repository.get_for_update(requirement_id, software_repository_id)
        if association is None:
            raise ErrNotFound()
        await self.repository.delete(association)
        await self.repository.commit()
        return {}

    async def _scope(
        self, user_id: str, requirement_id: str, *, action: ProjectAction
    ) -> tuple[Any, str]:
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound()
        await require_project_access(self.repository.session, user_id, project, action=action)
        return requirement, project.project_id

    async def _software_repository(
        self, project_id: str, software_repository_id: str
    ) -> SoftwareRepository:
        repository = await self.software_repositories.get(software_repository_id)
        if repository is None or repository.project_id != project_id:
            raise ErrNotFound()
        return repository

    async def _validate_branches(
        self,
        user_id: str,
        project_id: str,
        repository: SoftwareRepository,
        *,
        branch: str,
        baseline_branch: str,
        require_both: bool,
    ) -> None:
        values = [value for value in (branch, baseline_branch) if value.strip()]
        if require_both and len(values) != 2:
            raise ErrRequirementSoftwareRepositoryBranchRequired()
        if branch.strip() and baseline_branch.strip() and branch == baseline_branch:
            raise dynamic_error(ErrBadRequest, "基线分支不能与工作分支相同")
        if not values:
            return
        if self.connections is None:
            raise dynamic_error(ErrBadRequest, "未配置 GitLab 连接，无法校验分支")
        try:
            connection = await self.connections.resolve_personal_connection(
                user_id,
                "gitlab",
                project_id,
                repository.repository_instance_url,
            )
            for value in values:
                info = await self.connections.get_gitlab_branch(
                    connection.connection_id,
                    project_id,
                    repository.repository_project_id,
                    value,
                    user_id=user_id,
                )
                if str(info.get("name") or "") != value:
                    raise dynamic_error(
                        ErrRequirementSoftwareRepositoryBranchRequired,
                        f"分支 {value} 不存在或当前操作人无权访问",
                    )
        except AppError:
            raise
        except Exception as exc:
            raise dynamic_error(
                ErrRequirementSoftwareRepositoryBranchRequired,
                f"分支校验失败：{exc}",
            ) from exc
