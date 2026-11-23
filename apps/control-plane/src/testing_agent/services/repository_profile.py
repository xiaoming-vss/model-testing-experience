"""Repository profile snapshot assembly and result parsing.

Profiles are an optional, manually started analysis beside the requirement
generation chain. The run freezes the selected current or candidate
requirement-material content plus each active repository's working-branch HEAD.
Unlike code risk it does not need a baseline branch, diff, or existing test
cases.
"""

from __future__ import annotations

import logging
from typing import Any

from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    ErrResourceBindingInvalid,
    dynamic_error,
)
from testing_agent.domain.repository_profile import (
    PROFILE_REPOSITORY_FIELDS,
    PROFILE_ROLES,
    parse_repository_profile,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.requirement_software_repository import (
    RequirementRepositoryBinding,
    RequirementSoftwareRepositoryRepository,
    unique_by_git_repository,
)
from testing_agent.schemas.requirement import normalize_document_type
from testing_agent.services.generation_current_material import CurrentMaterial
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.repo_gitlab_access import resolve_repo_gitlab_access
from testing_agent.services.requirement_material_source import (
    material_reference_fields,
    material_source,
)

LOGGER = logging.getLogger(__name__)


class RepositoryProfileService:
    def __init__(
        self,
        task_repository: AiGenerateTaskRepository,
        requirement_repository: RequirementSoftwareRepositoryRepository,
        integration_connection_service: IntegrationConnectionService,
        credential_cipher: IntegrationCredentialCipher,
    ):
        self.task_repository = task_repository
        self.requirement_repository = requirement_repository
        self.integration_connection_service = integration_connection_service
        self.credential_cipher = credential_cipher

    async def build_snapshot(
        self,
        task: AiGenerateTask,
        run_id: str,
        worker_task_id: str,
        instruction: str | None = None,
        *,
        user_id: str,
        connection_ids: dict[str, str] | None = None,
        current_material: CurrentMaterial | None = None,
    ) -> dict[str, Any]:
        """Freeze the selected material content and working-branch repository pins."""
        requirement = await self.task_repository.get_requirement(task.requirement_id)
        if requirement is None:
            raise ErrNotFound()

        material = current_material
        if material is None:
            raise dynamic_error(ErrBadRequest, "请先审核通过材料整理，再进行仓库画像分析")

        bindings = unique_by_git_repository(
            await self.requirement_repository.list_for_requirement_with_repository(
                task.requirement_id
            )
        )
        if not bindings:
            raise dynamic_error(ErrResourceBindingInvalid, "需求尚未关联软件仓库，无法分析")

        entries = [
            await self._binding_entry(
                task,
                binding,
                user_id=user_id,
                connection_ids=connection_ids or {},
            )
            for binding in bindings
        ]
        document_type = normalize_document_type(str(requirement.document_type or "richtext"))
        return {
            "taskId": task.task_id,
            "runId": run_id,
            "taskType": task.task_type,
            "name": task.name,
            "projectId": task.project_id,
            "sprintId": task.sprint_id,
            "requirementId": task.requirement_id,
            "sourceType": task.source_type,
            "instruction": task.instruction if instruction is None else instruction,
            "requirement": {
                "requirementId": requirement.requirement_id,
                "name": requirement.name,
                "documentType": document_type,
                "documentContent": material_source(material),
            },
            **material_reference_fields(material),
            "bindings": entries,
            "gitlabCredentialsUrl": (
                f"/internal/ai-worker/tasks/{worker_task_id}/gitlab-credentials"
            ),
        }

    async def _binding_entry(
        self,
        task: AiGenerateTask,
        binding: RequirementRepositoryBinding,
        *,
        user_id: str,
        connection_ids: dict[str, str],
    ) -> dict[str, Any]:
        repository = binding.software_repository
        association = binding.association
        branch = association.branch.strip()
        fallback_path = repository.repository_path or repository.repository_name
        entry = {
            "bindingId": repository.software_repository_id,
            "softwareRepositoryId": repository.software_repository_id,
            "softwareRepositoryName": repository.name,
            "instanceUrl": repository.repository_instance_url,
            "repositoryId": repository.repository_project_id,
            "groupId": repository.repository_group_id,
            "pathWithNamespace": fallback_path,
            "branch": branch,
            "cloneUrl": "",
            "headCommit": "",
            "connectionId": "",
            "profileError": "",
        }
        if not branch:
            entry["profileError"] = "软件仓库关联缺少工作分支"
            return entry

        try:
            access = await resolve_repo_gitlab_access(
                self.integration_connection_service,
                self.credential_cipher,
                task.project_id,
                repository,
                user_id=user_id,
                connection_id=connection_ids.get(repository.repository_instance_url, ""),
            )
        except Exception as exc:
            _log_unavailable(task, repository.software_repository_id, "access", exc)
            entry["profileError"] = "未找到该仓库可用的 GitLab 个人授权"
            return entry

        try:
            project = await self.integration_connection_service.get_gitlab_project(
                access.connection_id,
                task.project_id,
                repository.repository_project_id,
                user_id=user_id,
            )
        except Exception as exc:
            _log_unavailable(task, repository.software_repository_id, "project", exc)
            entry["profileError"] = "GitLab 仓库不可访问"
            return entry

        clone_url = str(project.get("cloneUrl") or "").strip()
        if not clone_url:
            entry["profileError"] = "GitLab 仓库缺少克隆地址"
            return entry
        entry["pathWithNamespace"] = (
            str(project.get("pathWithNamespace") or "").strip() or fallback_path
        )

        try:
            head_commit = await self.integration_connection_service.resolve_gitlab_commit(
                access.connection_id,
                task.project_id,
                repository.repository_project_id,
                branch,
                user_id=user_id,
            )
        except Exception as exc:
            _log_unavailable(task, repository.software_repository_id, "commit", exc)
            entry["profileError"] = "工作分支不存在或无权限"
            return entry
        if not head_commit:
            entry["profileError"] = "无法解析仓库工作分支的最新提交"
            return entry

        entry.update(
            {
                "cloneUrl": clone_url,
                "headCommit": head_commit,
                "connectionId": access.connection_id,
            }
        )
        return entry


def _log_unavailable(
    task: AiGenerateTask, software_repository_id: str, stage: str, exc: Exception
) -> None:
    # Exception messages from remote clients can contain URLs or tokens; keep only the type.
    LOGGER.warning(
        "repository profile binding unavailable: task_id=%s "
        "software_repository_id=%s stage=%s error=%s",
        task.task_id,
        software_repository_id,
        stage,
        type(exc).__name__,
    )


__all__ = [
    "PROFILE_REPOSITORY_FIELDS",
    "PROFILE_ROLES",
    "RepositoryProfileService",
    "parse_repository_profile",
]
