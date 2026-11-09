"""Shared Git workspace primitives for read-only code analysis tasks.

Credentials are injected through a temporary askpass helper and never written to
the remote URL, ``.git/config``, logs, or prompts. Callers own the per-run
directory lifecycle and the higher-level task contract.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

from testing_agent_ai_worker.agent.paths import resolve_runtime_paths, resolve_task_workspace
from testing_agent_ai_worker.config.models import AgentBackendConfig
from testing_agent_ai_worker.models.task import GitlabCredentials, RepositoryBinding, Task


class GitWorkspaceError(RuntimeError):
    """Git workspace preparation failed; the message is safe to show to users."""


class GitRunner(Protocol):
    """Minimal git command runner so workspace tests can avoid real processes."""

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 300.0,
    ) -> str: ...


class SubprocessGitRunner:
    """Run git in its own process group with a hard timeout and bounded errors."""

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 300.0,
    ) -> str:
        process = subprocess.Popen(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise GitWorkspaceError(f"Git 操作超时（{timeout:.0f}s）") from exc
        if process.returncode != 0:
            detail = truncate((stderr or stdout or "").strip())
            raise GitWorkspaceError(f"Git 操作失败: {detail or '未知错误'}")
        return stdout


def task_run_root(agent_config: AgentBackendConfig, task: Task) -> Path:
    """Return the unique directory for this task attempt."""

    attempt = task.attempt_id or task.task_id
    # Strip separators at the edges so an attempt id such as ".." cannot
    # resolve to the task workspace itself.
    safe_attempt = re.sub(r"[^A-Za-z0-9._-]+", "-", attempt).strip("-.") or "attempt"
    return resolve_task_workspace(agent_config, task) / "runs" / safe_attempt


def retain_failed_workspace(run_root: Path, retention_hours: float) -> None:
    if not run_root.exists():
        return
    retain_until = datetime.now(UTC) + timedelta(hours=retention_hours)
    (run_root / ".retain-until").write_text(retain_until.isoformat(), encoding="utf-8")
    (run_root / ".active").unlink(missing_ok=True)


def sweep_expired_workspaces(
    agent_config: AgentBackendConfig,
    *,
    now: datetime | None = None,
) -> None:
    """Remove failed run workspaces whose retention window has expired."""

    current = now or datetime.now(UTC)
    workspaces_dir = resolve_runtime_paths(agent_config).workspaces_dir
    if not workspaces_dir.is_dir():
        return
    for marker in workspaces_dir.glob("*/task-*/runs/*/.retain-until"):
        try:
            retain_until = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if retain_until.tzinfo is None:
            retain_until = retain_until.replace(tzinfo=UTC)
        if retain_until <= current:
            shutil.rmtree(marker.parent, ignore_errors=True)


def clone_repository(
    binding: RepositoryBinding,
    repo_path: Path,
    env: dict[str, str],
    git: GitRunner,
    *,
    timeout: float,
) -> None:
    """Clone one repository without checking out a worktree."""

    if not binding.clone_url:
        raise GitWorkspaceError(f"仓库 {binding.repository_id} 缺少克隆地址")
    instance = urlsplit(binding.instance_url)
    clone = urlsplit(binding.clone_url)
    if instance.netloc and (
        clone.scheme.lower() != instance.scheme.lower()
        or clone.netloc.lower() != instance.netloc.lower()
    ):
        raise GitWorkspaceError(f"仓库 {binding.repository_id} 克隆地址与 GitLab 实例不一致")

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    git.run(
        [
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            "--no-recurse-submodules",
            "--quiet",
            authenticated_clone_url(binding.clone_url),
            str(repo_path),
        ],
        env=env,
        timeout=timeout,
    )


def checkout_head(
    git: GitRunner,
    repo_path: Path,
    binding: RepositoryBinding,
    commit: str,
    env: dict[str, str],
    *,
    timeout: float,
) -> None:
    """Detach at the pinned commit and verify the checked-out HEAD."""

    git.run(["checkout", "--detach", commit], cwd=repo_path, env=env, timeout=timeout)
    head = git.run(["rev-parse", "HEAD"], cwd=repo_path, env=env, timeout=timeout).strip()
    if head != commit:
        raise GitWorkspaceError(
            f"仓库 {binding.repository_id} HEAD {head} 与固定 headCommit 不一致"
        )


def fetch_commits(
    git: GitRunner,
    repo_path: Path,
    binding: RepositoryBinding,
    env: dict[str, str],
    timeout: float,
    *,
    commits: Sequence[str] | None = None,
) -> None:
    """Fetch branch refs first, then fall back to fetching exact commits."""

    refspecs: list[str] = []
    if binding.branch:
        refspecs.append(f"+refs/heads/{binding.branch}:refs/remotes/origin/{binding.branch}")
    if binding.baseline_branch:
        refspecs.append(
            f"+refs/heads/{binding.baseline_branch}:refs/remotes/origin/{binding.baseline_branch}"
        )
    if refspecs:
        try:
            git.run(
                ["fetch", "--filter=blob:none", "origin", *refspecs],
                cwd=repo_path,
                env=env,
                timeout=timeout,
            )
        except GitWorkspaceError:
            # Branch names can be stale; fall back to fetching the pinned SHAs directly.
            pass
    targets = list(commits) if commits is not None else [binding.base_commit, binding.head_commit]
    for commit in targets:
        if not commit:
            continue
        if has_commit(git, repo_path, commit, env, timeout):
            continue
        try:
            git.run(
                ["fetch", "--filter=blob:none", "origin", commit],
                cwd=repo_path,
                env=env,
                timeout=timeout,
            )
        except GitWorkspaceError as exc:
            raise GitWorkspaceError(
                f"仓库 {binding.repository_id} 无法获取 commit {commit}"
            ) from exc
        if not has_commit(git, repo_path, commit, env, timeout):
            raise GitWorkspaceError(f"仓库 {binding.repository_id} 缺少 commit {commit}")


def has_commit(
    git: GitRunner,
    repo_path: Path,
    commit: str,
    env: dict[str, str],
    timeout: float,
) -> bool:
    try:
        git.run(["cat-file", "-e", f"{commit}^{{commit}}"], cwd=repo_path, env=env, timeout=timeout)
    except GitWorkspaceError:
        return False
    return True


def git_env(auth_dir: Path, credential: GitlabCredentials) -> dict[str, str]:
    token = credential.access_token
    auth_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    askpass = auth_dir / "askpass.sh"
    askpass.write_text(
        '#!/bin/sh\ncase "$1" in\n  *Username*) printf "%s\\n" "${GIT_USERNAME}" ;;\n'
        '  *) printf "%s\\n" "${GIT_PASSWORD}" ;;\nesac\n',
        encoding="utf-8",
    )
    askpass.chmod(0o700)
    home = auth_dir / "home"
    home.mkdir(mode=0o700)
    config_global = auth_dir / "gitconfig"
    config_global.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(config_global),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": str(askpass),
            "GIT_USERNAME": "oauth2",
            "GIT_PASSWORD": token,
        }
    )
    return env


def authenticated_clone_url(clone_url: str) -> str:
    parsed = urlsplit(clone_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GitWorkspaceError("克隆地址必须是 HTTP(S) 地址")
    if parsed.username or parsed.password:
        raise GitWorkspaceError("克隆地址不能包含凭据")
    netloc = f"oauth2@{parsed.netloc}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def resolve_credential(
    binding: RepositoryBinding, credentials: Sequence[GitlabCredentials]
) -> GitlabCredentials | None:
    if binding.connection_id:
        return next(
            (c for c in credentials if c.connection_id == binding.connection_id),
            None,
        )
    return next(
        (c for c in credentials if binding.repository_id in c.repository_ids),
        None,
    )


def repo_directory_name(binding: RepositoryBinding) -> str:
    name = binding.path_with_namespace or binding.repository_id or "repo"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")[:80] or "repo"
    digest = hashlib.sha256(binding.binding_id.encode()).hexdigest()[:8]
    return f"{safe}-{digest}"


def truncate(value: str, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[:limit]}…"
