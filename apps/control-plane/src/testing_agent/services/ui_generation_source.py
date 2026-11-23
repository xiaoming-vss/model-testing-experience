"""Resolve UI generation source from the adopted repository profile.

A UI run copies the profile's repository pin into its own first-stage snapshot.
It uses the UI initiator's personal GitLab authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import AppError, ErrBadRequest, dynamic_error
from testing_agent.repositories.software_repository import SoftwareRepositoryRepository
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.repo_gitlab_access import (
    RepoGitlabAccess,
    resolve_repo_gitlab_access,
)

FRONTEND_ROLES = frozenset({"frontend", "fullstack"})
COMMIT_MODES = frozenset({"profile", "latest"})


@dataclass(frozen=True)
class ResolvedUiSource:
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
        integration_connection_service: IntegrationConnectionService,
        credential_cipher: IntegrationCredentialCipher,
    ) -> None:
        self.session = session
        self.integration_connection_service = integration_connection_service
        self.credential_cipher = credential_cipher

    @staticmethod
    def current_options(current: Any | None) -> dict[str, Any]:
        """Project one verified current profile without exposing its private bindings."""
        if current is None:
            return {
                "currentProfile": None,
                "defaultRepositoryId": "",
            }
        bindings = {str(binding.get("repositoryId") or ""): binding for binding in current.bindings}
        repositories = [
            _security_projection(repository, bindings.get(str(repository.get("repositoryId"))))
            for repository in current.profile.get("repositories") or []
            if isinstance(repository, dict)
        ]
        record = {
            "candidateId": current.candidate_id,
            "label": "当前画像",
            "sourceRunId": "",
            "createdAt": current.created_at,
            "overallSummary": str(current.profile.get("overallSummary") or ""),
            "repositories": repositories,
            "defaultRepositoryId": _default_repository(repositories),
        }
        return {
            "currentProfile": record,
            "defaultRepositoryId": record["defaultRepositoryId"],
        }

    async def resolve_current(
        self,
        *,
        current: Any,
        project_id: str,
        user_id: str,
        repository_id: str,
        commit_mode: str = "profile",
        gitlab_connection_id: str = "",
    ) -> ResolvedUiSource:
        """Resolve a verified current profile using the UI initiator's GitLab access.

        The caller must revalidate the current profile after remote GitLab reads
        and under the dispatch locks before using this pin.
        """
        repository, binding = self._current_repository(current, repository_id)
        return await self._resolve_selected(
            repository=repository,
            binding=binding,
            project_id=project_id,
            user_id=user_id,
            repository_id=repository_id,
            commit_mode=commit_mode,
            gitlab_connection_id=gitlab_connection_id,
        )

    async def _resolve_selected(
        self,
        *,
        repository: dict[str, Any],
        binding: dict[str, Any],
        project_id: str,
        user_id: str,
        repository_id: str,
        commit_mode: str,
        gitlab_connection_id: str,
    ) -> ResolvedUiSource:
        if commit_mode not in COMMIT_MODES:
            raise dynamic_error(ErrBadRequest, "不支持的源码 commit 模式")
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
        access = await self.resolve_binding_access(
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
            commit = await self.resolve_latest_commit(
                project_id, user_id, repository_id, branch, access
            )
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
            repository=pin,
            binding=worker_binding,
        )

    async def check_current(
        self,
        *,
        current: Any,
        project_id: str,
        user_id: str,
        repository_id: str,
        pinned_commit: str,
        gitlab_connection_id: str = "",
    ) -> dict[str, Any]:
        """Check a repository from a previously verified current profile."""
        _, binding = self._current_repository(current, repository_id)
        branch = str(binding.get("branch") or "").strip()
        if not branch:
            raise dynamic_error(ErrBadRequest, "当前画像中的仓库缺少工作分支")
        access = await self.resolve_binding_access(
            project_id, user_id, binding, gitlab_connection_id=gitlab_connection_id
        )
        head = await self.resolve_latest_commit(project_id, user_id, repository_id, branch, access)
        return {
            "repositoryId": repository_id,
            "branch": branch,
            "pinnedCommit": pinned_commit,
            "currentCommit": head,
            "changed": bool(pinned_commit) and head != pinned_commit,
        }

    async def rebind_frozen(
        self,
        *,
        repository: dict[str, Any],
        binding: dict[str, Any],
        project_id: str,
        user_id: str,
        gitlab_connection_id: str = "",
    ) -> dict[str, Any]:
        """Authorize a frozen pin for a new initiator without changing its commit.

        The caller must load both inputs from a server-owned candidate and
        revalidate its source closure under the dispatch locks after this remote
        read. Credentials and clone URLs are not part of the business pin.
        """
        repository_id = str(repository.get("repositoryId") or "")
        if (
            not repository_id
            or repository_id != binding.get("repositoryId")
            or any(
                not str(repository.get(key) or "").strip()
                for key in ("instanceUrl", "pathWithNamespace", "branch", "commit")
            )
            or repository.get("branch") != binding.get("branch")
        ):
            raise dynamic_error(ErrBadRequest, "已冻结的 UI 源码不可用，请重新生成")
        access = await self.resolve_binding_access(
            project_id, user_id, binding, gitlab_connection_id=gitlab_connection_id
        )
        if (
            access.base_url.rstrip("/").lower()
            != str(repository["instanceUrl"]).rstrip("/").lower()
        ):
            raise dynamic_error(ErrBadRequest, "已冻结的 UI 仓库地址已变化，请重新生成")
        project = await self._project(project_id, user_id, repository_id, access)
        clone_url = str(project.get("cloneUrl") or "").strip()
        path = str(project.get("pathWithNamespace") or "").strip()
        if not clone_url or path != repository["pathWithNamespace"]:
            raise dynamic_error(ErrBadRequest, "已冻结的 UI 仓库不可用或路径已变化，请重新生成")
        return {
            **binding,
            "headCommit": repository["commit"],
            "cloneUrl": clone_url,
            "connectionId": access.connection_id,
        }

    @staticmethod
    def _current_repository(
        current: Any, repository_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        repository = next(
            (
                item
                for item in current.profile.get("repositories", [])
                if isinstance(item, dict) and item.get("repositoryId") == repository_id
            ),
            None,
        )
        binding = next(
            (item for item in current.bindings if item.get("repositoryId") == repository_id), None
        )
        if not repository or not _frontend(repository.get("role")) or not binding:
            raise dynamic_error(ErrBadRequest, "所选仓库不属于当前画像")
        if binding.get("profileError"):
            raise dynamic_error(ErrBadRequest, "当前画像中的仓库不可用，请重新生成画像")
        return repository, binding

    async def resolve_binding_access(
        self,
        project_id: str,
        user_id: str,
        binding: dict[str, Any],
        *,
        gitlab_connection_id: str,
    ) -> RepoGitlabAccess:
        row = await SoftwareRepositoryRepository(self.session).get(
            str(binding.get("softwareRepositoryId") or binding.get("bindingId") or "")
        )
        if (
            row is None
            or row.project_id != project_id
            or str(row.repository_project_id or "") != str(binding.get("repositoryId") or "")
        ):
            raise dynamic_error(
                ErrBadRequest,
                "软件仓库已失效，请重新关联或重新生成画像",
                {"reason": "repository_unavailable"},
            )
        try:
            return await resolve_repo_gitlab_access(
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

    async def resolve_latest_commit(
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
