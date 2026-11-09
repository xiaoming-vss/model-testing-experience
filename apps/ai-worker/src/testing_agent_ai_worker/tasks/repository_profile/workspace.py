"""Per-run checkout for repository profile analysis.

Only the working-branch HEAD is needed. Repository failures are isolated: an
unreadable repository is reported as unavailable while the other repositories
remain available to the agent.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

from testing_agent_ai_worker.config.models import AgentBackendConfig, RepositoryProfileConfig
from testing_agent_ai_worker.models.task import GitlabCredentials, RepositoryBinding, Task
from testing_agent_ai_worker.tasks.git_workspace import (
    GitRunner,
    GitWorkspaceError,
    SubprocessGitRunner,
    checkout_head,
    clone_repository,
    fetch_commits,
    git_env,
    repo_directory_name,
    resolve_credential,
    retain_failed_workspace,
    sweep_expired_workspaces,
    task_run_root,
)

LOGGER = logging.getLogger("testing_agent_ai_worker")


class ProfileWorkspaceError(RuntimeError):
    """Repository profile workspace preparation failed with a safe message."""


@dataclass(slots=True)
class ProfileRepoWorkspace:
    binding: RepositoryBinding
    path: Path
    head_commit: str
    order: int
    top_level_entries: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UnavailableRepository:
    binding: RepositoryBinding
    error: str
    order: int


@dataclass(slots=True)
class ProfileWorkspace:
    run_root: Path
    code_root: Path
    repositories: list[ProfileRepoWorkspace]
    unavailable: list[UnavailableRepository]

    @property
    def manifest(self) -> dict[str, object]:
        return {
            "repositories": [
                {
                    "bindingId": repo.binding.binding_id,
                    "repositoryId": repo.binding.repository_id,
                    "instanceUrl": repo.binding.instance_url,
                    "pathWithNamespace": repo.binding.path_with_namespace,
                    "branch": repo.binding.branch,
                    "headCommit": repo.head_commit,
                    "localPath": repo.path.relative_to(self.code_root).as_posix(),
                    "topLevelEntries": repo.top_level_entries,
                }
                for repo in self.repositories
            ],
            "unavailable": [
                {
                    "bindingId": item.binding.binding_id,
                    "repositoryId": item.binding.repository_id,
                    "pathWithNamespace": item.binding.path_with_namespace,
                    "error": item.error,
                }
                for item in self.unavailable
            ],
        }


def prepare_profile_workspace(
    task: Task,
    credentials: Sequence[GitlabCredentials],
    *,
    agent_config: AgentBackendConfig,
    config: RepositoryProfileConfig,
    runner: GitRunner | None = None,
    now: datetime | None = None,
) -> ProfileWorkspace:
    """Clone every analyzable repository at its working-branch HEAD.

    One repository failure marks that repository unavailable; all failures abort
    the run. The caller removes the workspace on success or retains it on failure.
    """

    if not task.bindings:
        raise ProfileWorkspaceError("需求未绑定代码仓库，无法准备仓库画像")
    if len(task.bindings) > config.max_repos:
        raise ProfileWorkspaceError(f"仓库数量超过上限（{config.max_repos}）")

    run_root = task_run_root(agent_config, task)
    sweep_expired_workspaces(agent_config, now=now)
    if run_root.exists():
        shutil.rmtree(run_root, ignore_errors=True)
    code_root = run_root / "code"
    code_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (run_root / ".active").write_text("1", encoding="utf-8")

    git = runner or SubprocessGitRunner()
    repositories: list[ProfileRepoWorkspace] = []
    unavailable: list[UnavailableRepository] = []
    auth_root = Path(tempfile.mkdtemp(prefix=".git-auth-", dir=run_root))
    try:
        for index, binding in enumerate(task.bindings):
            if binding.profile_error:
                unavailable.append(UnavailableRepository(binding, binding.profile_error, index))
                continue
            if not binding.clone_url or not binding.head_commit:
                unavailable.append(
                    UnavailableRepository(binding, "仓库缺少克隆地址或工作分支 HEAD", index)
                )
                continue
            credential = resolve_credential(binding, credentials)
            if credential is None:
                unavailable.append(
                    UnavailableRepository(binding, "未匹配到该仓库的 GitLab 凭据", index)
                )
                continue
            repo_path = code_root / "repos" / repo_directory_name(binding)
            env = git_env(auth_root / f"repo-{index}", credential)
            try:
                clone_repository(binding, repo_path, env, git, timeout=config.git_timeout_seconds)
                fetch_commits(
                    git,
                    repo_path,
                    binding,
                    env,
                    config.git_timeout_seconds,
                    commits=(binding.head_commit,),
                )
                checkout_head(
                    git,
                    repo_path,
                    binding,
                    binding.head_commit,
                    env,
                    timeout=config.git_timeout_seconds,
                )
                repositories.append(
                    ProfileRepoWorkspace(
                        binding=binding,
                        path=repo_path,
                        head_commit=binding.head_commit,
                        order=index,
                        top_level_entries=_top_level_entries(repo_path),
                    )
                )
            except GitWorkspaceError as exc:
                shutil.rmtree(repo_path, ignore_errors=True)
                unavailable.append(UnavailableRepository(binding, str(exc), index))
                LOGGER.warning(
                    "repository profile repo unavailable: task_id=%s binding_id=%s error=%s",
                    task.task_id,
                    binding.binding_id,
                    type(exc).__name__,
                )
        if not repositories:
            raise ProfileWorkspaceError("所有绑定仓库均无法读取，无法生成仓库画像")
        workspace = ProfileWorkspace(
            run_root=run_root,
            code_root=code_root,
            repositories=repositories,
            unavailable=unavailable,
        )
        (code_root / "manifest.json").write_text(
            json.dumps(workspace.manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return workspace
    finally:
        shutil.rmtree(auth_root, ignore_errors=True)


def cleanup_profile_workspace(
    workspace: ProfileWorkspace,
    *,
    success: bool,
    config: RepositoryProfileConfig,
) -> None:
    if success:
        shutil.rmtree(workspace.run_root, ignore_errors=True)
        return
    retain_failed_workspace(workspace.run_root, config.workspace_retention_hours)


def _top_level_entries(repo_path: Path, limit: int = 200) -> list[str]:
    entries: list[str] = []
    try:
        children = sorted(repo_path.iterdir(), key=lambda item: (not item.is_dir(), item.name))
    except OSError:
        return entries
    for child in children:
        if child.name == ".git":
            continue
        entries.append(f"{child.name}/" if child.is_dir() else child.name)
        if len(entries) >= limit:
            break
    return entries
