"""Resolve UI generation source from an immutable repository profile version.

A UI run copies the profile's repository pin into its own first-stage snapshot.
It never follows the profile run afterwards, and it always uses the UI
initiator's personal GitLab authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import AppError, ErrBadRequest, dynamic_error
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.repo_gitlab_access import (
    RepoGitlabAccess,
    resolve_repo_gitlab_access,
)
from testing_agent.services.repository_profile_versions import list_profile_version_records

FRONTEND_ROLES = frozenset({"frontend", "fullstack"})
COMMIT_MODES = frozenset({"profile", "latest"})


@dataclass(frozen=True)
class ResolvedUiSource:
    profile_version_id: str
    profile_version_no: int
    repository: dict[str, Any]
    binding: dict[str, Any]


def _frontend(role: Any) -> bool:
    return isinstance(role, str) and role in FRONTEND_ROLES


def _security_projection(
    repository: dict[str, Any], binding: dict[str, Any] | None
) -> dict[str, Any]:
    role = repository.get("role")
    profile_error = str((binding or {}).get("profileError") or "")
    branch = str((binding or {}).get("branch") or "")
    commit = str((binding or {}).get("headCommit") or "")
    is_frontend = _frontend(role)
    return {
        "repositoryId": str(repository.get("repositoryId") or ""),
        "pathWithNamespace": str(repository.get("pathWithNamespace") or ""),
        "role": str(role or "unknown"),
        "confidence": repository.get("confidence"),
        "responsibilitySummary": str(repository.get("responsibilitySummary") or ""),
        "techStack": list(repository.get("techStack") or []),
        "keyPaths": list(repository.get("keyPaths") or []),
        "branch": branch,
        "commit": commit,
        "isFrontend": is_frontend,
        "available": bool(is_frontend and binding and not profile_error and branch and commit),
        "profileError": profile_error,
    }


def _default_repository(repositories: list[dict[str, Any]]) -> str:
    candidates = [item for item in repositories if item["available"]]
    if not candidates:
        return ""
    return max(candidates, key=lambda item: float(item.get("confidence") or 0))["repositoryId"]


class UiGenerationSourceService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        binding_repository: ResourceBindingRepository,
        integration_connection_service: IntegrationConnectionService,
        credential_cipher: IntegrationCredentialCipher,
    ) -> None:
        self.session = session
        self.binding_repository = binding_repository
        self.integration_connection_service = integration_connection_service
        self.credential_cipher = credential_cipher

    async def options(self, requirement_id: str) -> dict[str, Any]:
        """List successful profile versions and safe repository projections.

        This read never calls GitLab; availability reflects only the frozen
        profile snapshot so opening the chain does not fan out remote requests.
        """
        task = await GenerationChainRepository(self.session).task(
            requirement_id, "repository_profile"
        )
        if task is None:
            return {
                "profileVersions": [],
                "defaultProfileVersionId": "",
                "defaultRepositoryId": "",
            }
        records = await list_profile_version_records(
            self.session, task.task_id, include_bindings=True
        )
        versions: list[dict[str, Any]] = []
        for record in records:
            profile = record.get("profile") or {}
            bindings = {
                str(binding.get("repositoryId") or ""): binding
                for binding in record.get("bindings") or []
                if isinstance(binding, dict)
            }
            repositories = [
                _security_projection(repository, bindings.get(str(repository.get("repositoryId"))))
                for repository in profile.get("repositories") or []
                if isinstance(repository, dict)
            ]
            versions.append(
                {
                    "versionId": record["versionId"],
                    "versionNo": record["versionNo"],
                    "label": record["label"],
                    "sourceRunId": record["sourceRunId"],
                    "createdAt": record["createdAt"],
                    "overallSummary": str(profile.get("overallSummary") or ""),
                    "repositories": repositories,
                    "defaultRepositoryId": _default_repository(repositories),
                }
            )
        latest = versions[0] if versions else None
        return {
            "profileVersions": versions,
            "defaultProfileVersionId": latest["versionId"] if latest else "",
            "defaultRepositoryId": latest["defaultRepositoryId"] if latest else "",
        }

    async def resolve(
        self,
        *,
        requirement_id: str,
        project_id: str,
        user_id: str,
        profile_version_id: str,
        repository_id: str,
        commit_mode: str = "profile",
        gitlab_connection_id: str = "",
    ) -> ResolvedUiSource:
        if commit_mode not in COMMIT_MODES:
            raise dynamic_error(ErrBadRequest, "不支持的源码 commit 模式")
        version, repository, binding = await self._select(
            requirement_id, profile_version_id, repository_id
        )
        if not _frontend(repository.get("role")):
            raise dynamic_error(
                ErrBadRequest,
                "所选仓库不是前端或全栈仓库，请重新选择",
                {"reason": "not_frontend"},
            )
        branch = str(binding.get("branch") or "").strip()
        if not branch:
            raise dynamic_error(
                ErrBadRequest,
                "仓库绑定缺少工作分支，请检查仓库绑定",
                {"reason": "repository_unavailable"},
            )
        access = await self._access(
            project_id, user_id, binding, gitlab_connection_id=gitlab_connection_id
        )
        project = await self._project(project_id, user_id, repository_id, access)
        clone_url = str(project.get("cloneUrl") or "").strip()
        if not clone_url:
            raise dynamic_error(
                ErrBadRequest,
                "GitLab 仓库缺少克隆地址，请重新选择",
                {"reason": "repository_unavailable"},
            )
        if commit_mode == "latest":
            commit = await self._latest_commit(project_id, user_id, repository_id, branch, access)
        else:
            commit = str(binding.get("headCommit") or "").strip()
            if not commit:
                raise dynamic_error(
                    ErrBadRequest,
                    "仓库画像未冻结该仓库的 commit，请重新生成画像或切换最新 HEAD",
                    {"reason": "commit_unavailable"},
                )
        path = (
            str(project.get("pathWithNamespace") or "").strip()
            or str(binding.get("pathWithNamespace") or "").strip()
            or str(repository.get("pathWithNamespace") or "").strip()
        )
        resolved_at = datetime.now(UTC).isoformat()
        pin = {
            "bindingId": str(binding.get("bindingId") or ""),
            "repositoryId": repository_id,
            "instanceUrl": str(binding.get("instanceUrl") or ""),
            "pathWithNamespace": path,
            "branch": branch,
            "commit": commit,
            "commitMode": commit_mode,
            "resolvedAt": resolved_at,
        }
        worker_binding = {
            "bindingId": pin["bindingId"],
            "repositoryId": repository_id,
            "instanceUrl": pin["instanceUrl"],
            "pathWithNamespace": path,
            "branch": branch,
            "headCommit": commit,
            "cloneUrl": clone_url,
            "connectionId": access.connection_id,
            "profileError": "",
        }
        return ResolvedUiSource(
            profile_version_id=version["versionId"],
            profile_version_no=int(version["versionNo"]),
            repository=pin,
            binding=worker_binding,
        )

    async def check(
        self,
        *,
        requirement_id: str,
        project_id: str,
        user_id: str,
        profile_version_id: str,
        repository_id: str,
        pinned_commit: str,
        gitlab_connection_id: str = "",
    ) -> dict[str, Any]:
        """Resolve the branch HEAD now without mutating the frozen run."""
        _, _, binding = await self._select(requirement_id, profile_version_id, repository_id)
        branch = str(binding.get("branch") or "").strip()
        if not branch:
            raise dynamic_error(
                ErrBadRequest,
                "仓库绑定缺少工作分支，请检查仓库绑定",
                {"reason": "repository_unavailable"},
            )
        access = await self._access(
            project_id, user_id, binding, gitlab_connection_id=gitlab_connection_id
        )
        current = await self._latest_commit(project_id, user_id, repository_id, branch, access)
        return {
            "repositoryId": repository_id,
            "branch": branch,
            "pinnedCommit": pinned_commit,
            "currentCommit": current,
            "changed": bool(pinned_commit) and current != pinned_commit,
        }

    async def _select(
        self, requirement_id: str, profile_version_id: str, repository_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        task = await GenerationChainRepository(self.session).task(
            requirement_id, "repository_profile"
        )
        if task is None:
            raise dynamic_error(
                ErrBadRequest,
                "请先生成仓库画像，再开始 UI 用例生成",
                {"reason": "no_profile"},
            )
        records = await list_profile_version_records(
            self.session, task.task_id, include_bindings=True
        )
        version = next(
            (record for record in records if record["versionId"] == profile_version_id), None
        )
        if version is None or not isinstance(version.get("profile"), dict):
            raise dynamic_error(
                ErrBadRequest,
                "所选仓库画像版本不存在或内容不可用，请重新选择",
                {"reason": "profile_version_unavailable"},
            )
        repository = next(
            (
                item
                for item in version["profile"].get("repositories") or []
                if isinstance(item, dict) and str(item.get("repositoryId") or "") == repository_id
            ),
            None,
        )
        if repository is None:
            raise dynamic_error(
                ErrBadRequest,
                "所选仓库不在该画像版本中，请重新选择",
                {"reason": "repository_unavailable"},
            )
        binding = next(
            (
                item
                for item in version.get("bindings") or []
                if isinstance(item, dict) and str(item.get("repositoryId") or "") == repository_id
            ),
            None,
        )
        if binding is None:
            raise dynamic_error(
                ErrBadRequest,
                "仓库画像没有该仓库的源码绑定，请检查仓库绑定或重新生成画像",
                {"reason": "repository_unavailable"},
            )
        profile_error = str(binding.get("profileError") or "").strip()
        if profile_error:
            raise dynamic_error(
                ErrBadRequest,
                f"{profile_error}，请检查仓库绑定或重新生成画像",
                {"reason": "repository_unavailable"},
            )
        return version, repository, binding

    async def _access(
        self,
        project_id: str,
        user_id: str,
        binding: dict[str, Any],
        *,
        gitlab_connection_id: str,
    ) -> RepoGitlabAccess:
        from sqlalchemy import select

        from testing_agent.models.resource_binding import ResourceBinding

        row = await self.session.scalar(
            select(ResourceBinding).where(
                ResourceBinding.binding_id == str(binding.get("bindingId") or "")
            )
        )
        if row is None:
            raise dynamic_error(
                ErrBadRequest,
                "仓库绑定已失效，请重新绑定或重新生成画像",
                {"reason": "repository_unavailable"},
            )
        try:
            return await resolve_repo_gitlab_access(
                self.binding_repository,
                self.integration_connection_service,
                self.credential_cipher,
                project_id,
                row,
                user_id=user_id,
                connection_id=gitlab_connection_id,
            )
        except AppError as exc:
            raise dynamic_error(
                ErrBadRequest,
                "未找到所选仓库的 GitLab 个人授权，请先配置",
                {"reason": "gitlab_access", "detail": exc.message},
            ) from exc

    async def _project(
        self,
        project_id: str,
        user_id: str,
        repository_id: str,
        access: RepoGitlabAccess,
    ) -> dict[str, Any]:
        try:
            return await self.integration_connection_service.get_gitlab_project(
                access.connection_id,
                project_id,
                repository_id,
                user_id=user_id,
            )
        except AppError as exc:
            raise dynamic_error(
                ErrBadRequest,
                "GitLab 仓库不可访问，请检查仓库绑定和授权",
                {"reason": "repository_unavailable", "detail": exc.message},
            ) from exc

    async def _latest_commit(
        self,
        project_id: str,
        user_id: str,
        repository_id: str,
        branch: str,
        access: RepoGitlabAccess,
    ) -> str:
        try:
            commit = await self.integration_connection_service.resolve_gitlab_commit(
                access.connection_id,
                project_id,
                repository_id,
                branch,
                user_id=user_id,
            )
        except AppError as exc:
            raise dynamic_error(
                ErrBadRequest,
                "无法解析仓库分支最新提交，请检查分支与权限",
                {"reason": "commit_unavailable", "detail": exc.message},
            ) from exc
        if not commit:
            raise dynamic_error(
                ErrBadRequest,
                "无法解析仓库分支最新提交，请检查分支与权限",
                {"reason": "commit_unavailable"},
            )
        return str(commit)


__all__ = ["COMMIT_MODES", "FRONTEND_ROLES", "ResolvedUiSource", "UiGenerationSourceService"]
