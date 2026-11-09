"""Repository profile snapshot assembly and result parsing.

Profiles are an optional, manually started analysis beside the requirement
generation chain. The run freezes the selected approved requirement-understanding
version plus each active repository's working-branch HEAD. Unlike code risk it
does not need a baseline branch, diff, or existing test cases.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    ErrResourceBindingInvalid,
    dynamic_error,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.schemas.requirement import normalize_document_type
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.repo_gitlab_access import resolve_repo_gitlab_access
from testing_agent.services.requirement_understanding_source import (
    approved_understanding,
    understanding_source,
    understanding_version_ref,
)

LOGGER = logging.getLogger(__name__)

PROFILE_ROLES = frozenset({"frontend", "backend", "fullstack", "infra", "test", "unknown"})
PROFILE_REPOSITORY_FIELDS = (
    "repositoryId",
    "pathWithNamespace",
    "role",
    "responsibilitySummary",
    "techStack",
    "keyPaths",
    "confidence",
    "evidence",
)


class RepositoryProfileService:
    def __init__(
        self,
        task_repository: AiGenerateTaskRepository,
        binding_repository: ResourceBindingRepository,
        integration_connection_service: IntegrationConnectionService,
        credential_cipher: IntegrationCredentialCipher,
    ):
        self.task_repository = task_repository
        self.binding_repository = binding_repository
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
        understanding_version_id: str = "",
    ) -> dict[str, Any]:
        """Freeze the approved understanding source and working-branch repository pins."""
        requirement = await self.task_repository.get_requirement(task.requirement_id)
        if requirement is None:
            raise ErrNotFound()

        understanding = await approved_understanding(
            GenerationChainRepository(self.task_repository.session),
            task.requirement_id,
            understanding_version_id,
        )
        if understanding is None:
            raise dynamic_error(ErrBadRequest, "请先审核通过需求理解，再进行仓库画像分析")

        bindings = list(
            await self.binding_repository.list_active_repo_bindings_for_requirement(
                task.requirement_id
            )
        )
        if not bindings:
            raise dynamic_error(ErrResourceBindingInvalid, "需求尚未绑定代码仓库，无法分析")

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
                "documentContent": understanding_source(understanding),
            },
            "requirementUnderstandingVersion": understanding_version_ref(understanding),
            "bindings": entries,
            "gitlabCredentialsUrl": (
                f"/internal/ai-worker/tasks/{worker_task_id}/gitlab-credentials"
            ),
        }

    async def _binding_entry(
        self,
        task: AiGenerateTask,
        binding: ResourceBinding,
        *,
        user_id: str,
        connection_ids: dict[str, str],
    ) -> dict[str, Any]:
        extra = binding.extra_json or {}
        branch = str(extra.get("branch") or "").strip()
        fallback_path = binding.remote_name_snapshot or binding.remote_resource_id
        entry = {
            "bindingId": binding.binding_id,
            "instanceUrl": binding.instance_url,
            "repositoryId": binding.remote_resource_id,
            "groupId": binding.remote_parent_id or "",
            "pathWithNamespace": fallback_path,
            "branch": branch,
            "cloneUrl": "",
            "headCommit": "",
            "connectionId": "",
            "profileError": "",
        }
        if not branch:
            entry["profileError"] = "仓库绑定缺少工作分支"
            return entry

        try:
            access = await resolve_repo_gitlab_access(
                self.binding_repository,
                self.integration_connection_service,
                self.credential_cipher,
                task.project_id,
                binding,
                user_id=user_id,
                connection_id=connection_ids.get(binding.instance_url, ""),
            )
        except Exception as exc:
            _log_unavailable(task, binding, "access", exc)
            entry["profileError"] = "未找到该仓库可用的 GitLab 个人授权"
            return entry

        try:
            project = await self.integration_connection_service.get_gitlab_project(
                access.connection_id,
                task.project_id,
                binding.remote_resource_id,
                user_id=user_id,
            )
        except Exception as exc:
            _log_unavailable(task, binding, "project", exc)
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
                binding.remote_resource_id,
                branch,
                user_id=user_id,
            )
        except Exception as exc:
            _log_unavailable(task, binding, "commit", exc)
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
    task: AiGenerateTask, binding: ResourceBinding, stage: str, exc: Exception
) -> None:
    # Exception messages from remote clients can contain URLs or tokens; keep only the type.
    LOGGER.warning(
        "repository profile binding unavailable: task_id=%s binding_id=%s stage=%s error=%s",
        task.task_id,
        binding.binding_id,
        stage,
        type(exc).__name__,
    )


def parse_repository_profile(result_json: str | None) -> dict[str, Any] | None:
    """Parse the worker's exact profile JSON; malformed content stays readable as raw."""
    raw = str(result_json or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or set(data) != {"repositories", "overallSummary"}:
        return None
    repositories = data.get("repositories")
    overall_summary = data.get("overallSummary")
    if not isinstance(repositories, list) or not isinstance(overall_summary, str):
        return None
    if not overall_summary.strip():
        return None
    normalized: list[dict[str, Any]] = []
    for item in repositories:
        if not isinstance(item, dict):
            return None
        if set(item) != set(PROFILE_REPOSITORY_FIELDS):
            return None
        repository_id = item.get("repositoryId")
        path = item.get("pathWithNamespace")
        role = item.get("role")
        responsibility = item.get("responsibilitySummary")
        tech_stack = item.get("techStack")
        key_paths = item.get("keyPaths")
        confidence = item.get("confidence")
        evidence = item.get("evidence")
        if not isinstance(repository_id, str) or not repository_id.strip():
            return None
        if not isinstance(path, str) or not path.strip():
            return None
        if role not in PROFILE_ROLES:
            return None
        if not isinstance(responsibility, str) or not responsibility.strip():
            return None
        if (
            not _string_list(tech_stack)
            or not _string_list(key_paths)
            or not _string_list(evidence)
        ):
            return None
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= float(confidence) <= 1
        ):
            return None
        normalized.append(
            {
                "repositoryId": repository_id.strip(),
                "pathWithNamespace": path.strip(),
                "role": role,
                "responsibilitySummary": responsibility.strip(),
                "techStack": tech_stack,
                "keyPaths": key_paths,
                "confidence": float(confidence),
                "evidence": evidence,
            }
        )
    return {"repositories": normalized, "overallSummary": overall_summary.strip()}


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


__all__ = [
    "PROFILE_REPOSITORY_FIELDS",
    "PROFILE_ROLES",
    "RepositoryProfileService",
    "parse_repository_profile",
]
