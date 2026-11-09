"""Per-run Git code workspace for code risk analysis.

The worker clones each requirement repository at the pinned base/head commits,
generates a local diff, and leaves the checkout available to the read-only
agent. Credentials are injected through a temporary askpass helper and are
never written to the remote URL, ``.git/config``, logs, or prompts.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from testing_agent_ai_worker.config.models import AgentBackendConfig, CodeRiskAnalysisConfig
from testing_agent_ai_worker.models.task import GitlabCredentials, RepositoryBinding, Task
from testing_agent_ai_worker.tasks.code_risk_analysis.diff_prep import (
    compute_diffstat,
    filter_diff_files,
)
from testing_agent_ai_worker.tasks.git_workspace import (
    GitRunner,
    SubprocessGitRunner,
    checkout_head,
    clone_repository,
    retain_failed_workspace,
    sweep_expired_workspaces,
)
from testing_agent_ai_worker.tasks.git_workspace import (
    GitWorkspaceError as CodeWorkspaceError,
)
from testing_agent_ai_worker.tasks.git_workspace import (
    fetch_commits as _fetch_pinned_commits,
)
from testing_agent_ai_worker.tasks.git_workspace import (
    git_env as _git_env,
)
from testing_agent_ai_worker.tasks.git_workspace import (
    repo_directory_name as _repo_directory_name,
)
from testing_agent_ai_worker.tasks.git_workspace import (
    resolve_credential as _resolve_credential,
)
from testing_agent_ai_worker.tasks.git_workspace import (
    task_run_root as code_run_root,
)

DIFF_HEADER = re.compile(r"^diff --git a/(.*?) b/(.*?)$", re.MULTILINE)


@dataclass(slots=True)
class RepoWorkspace:
    binding: RepositoryBinding
    path: Path
    base_commit: str
    head_commit: str
    changed_files: list[str]
    diff_files: list[dict[str, Any]]
    files_changed: int
    additions: int
    deletions: int


@dataclass(slots=True)
class CodeWorkspace:
    run_root: Path
    code_root: Path
    repositories: list[RepoWorkspace]

    @property
    def manifest(self) -> dict[str, Any]:
        return {
            "repositories": [
                {
                    "bindingId": repo.binding.binding_id,
                    "repositoryId": repo.binding.repository_id,
                    "instanceUrl": repo.binding.instance_url,
                    "pathWithNamespace": repo.binding.path_with_namespace,
                    "branch": repo.binding.branch,
                    "baselineBranch": repo.binding.baseline_branch,
                    "baseCommit": repo.base_commit,
                    "headCommit": repo.head_commit,
                    "localPath": repo.path.relative_to(self.code_root).as_posix(),
                    "changedFiles": repo.changed_files,
                    "filesChanged": repo.files_changed,
                    "additions": repo.additions,
                    "deletions": repo.deletions,
                }
                for repo in self.repositories
            ]
        }


def prepare_code_workspace(
    task: Task,
    credentials: Sequence[GitlabCredentials],
    *,
    agent_config: AgentBackendConfig,
    config: CodeRiskAnalysisConfig,
    runner: GitRunner | None = None,
    now: datetime | None = None,
) -> CodeWorkspace:
    """Clone all bound repositories at pinned commits and build local diffs.

    Any repository failure aborts the whole run. The workspace is marked active
    and is either removed on success or retained with a TTL by the caller.
    """

    if not task.bindings:
        raise CodeWorkspaceError("需求未绑定代码仓库，无法准备代码上下文")
    if len(task.bindings) > config.max_repos:
        raise CodeWorkspaceError(f"仓库数量超过上限（{config.max_repos}）")

    run_root = code_run_root(agent_config, task)
    sweep_expired_workspaces(agent_config, now=now)
    if run_root.exists():
        shutil.rmtree(run_root, ignore_errors=True)
    code_root = run_root / "code"
    code_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (run_root / ".active").write_text("1", encoding="utf-8")

    git = runner or SubprocessGitRunner()
    repos: list[RepoWorkspace] = []
    auth_root = Path(tempfile.mkdtemp(prefix=".git-auth-", dir=run_root))
    try:
        for index, binding in enumerate(task.bindings):
            credential = _resolve_credential(binding, credentials)
            if credential is None:
                raise CodeWorkspaceError(f"仓库 {binding.repository_id} 未匹配到 GitLab 凭据")
            env = _git_env(auth_root / f"repo-{index}", credential)
            repos.append(
                _prepare_repository(
                    binding,
                    code_root,
                    env,
                    git,
                    timeout=config.git_timeout_seconds,
                )
            )
        workspace = CodeWorkspace(run_root=run_root, code_root=code_root, repositories=repos)
        (code_root / "manifest.json").write_text(
            json.dumps(workspace.manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return workspace
    finally:
        shutil.rmtree(auth_root, ignore_errors=True)


def cleanup_code_workspace(
    workspace: CodeWorkspace,
    *,
    success: bool,
    config: CodeRiskAnalysisConfig,
) -> None:
    """Delete successful runs and retain failed ones for debugging."""

    if success:
        shutil.rmtree(workspace.run_root, ignore_errors=True)
        return
    retain_failed_workspace(workspace.run_root, config.workspace_retention_hours)


def _prepare_repository(
    binding: RepositoryBinding,
    code_root: Path,
    env: dict[str, str],
    git: GitRunner,
    *,
    timeout: float,
) -> RepoWorkspace:
    if not binding.base_commit or not binding.head_commit:
        raise CodeWorkspaceError(f"仓库 {binding.repository_id} 缺少固定的 base/head commit")

    repo_path = code_root / "repos" / _repo_directory_name(binding)
    clone_repository(binding, repo_path, env, git, timeout=timeout)
    _fetch_pinned_commits(git, repo_path, binding, env, timeout)
    checkout_head(git, repo_path, binding, binding.head_commit, env, timeout=timeout)

    diff_text = git.run(
        [
            "-c",
            "core.quotePath=false",
            "diff",
            "--no-color",
            "--no-ext-diff",
            "--unified=3",
            binding.base_commit,
            binding.head_commit,
        ],
        cwd=repo_path,
        env=env,
        timeout=timeout,
    )
    raw_diff_files = _split_git_diff(diff_text)
    changed_files = _changed_files(raw_diff_files)
    filtered = filter_diff_files(raw_diff_files)
    files_changed, additions, deletions = compute_diffstat(raw_diff_files)
    return RepoWorkspace(
        binding=binding,
        path=repo_path,
        base_commit=binding.base_commit,
        head_commit=binding.head_commit,
        changed_files=changed_files,
        diff_files=filtered,
        files_changed=files_changed,
        additions=additions,
        deletions=deletions,
    )


def _split_git_diff(diff_text: str) -> list[dict[str, Any]]:
    matches = list(DIFF_HEADER.finditer(diff_text))
    if not matches:
        return []
    files: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(diff_text)
        files.append(
            {
                "old_path": match.group(1),
                "new_path": match.group(2),
                "diff": diff_text[match.start() : end],
            }
        )
    return files


def _changed_files(diff_files: Sequence[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for item in diff_files:
        path = str(item.get("new_path") or item.get("old_path") or "").strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _truncate(value: str, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[:limit]}…"
