"""Pinned repository checkout for UI generation source.

UI 生成的新来源是一个已经由控制面冻结的仓库 commit。这里只复用共享 Git 原语:
`--filter=blob:none --no-checkout` 克隆,拉取分支与精确 commit,detached checkout 后
校验 HEAD,最后删除 `.git` 目录,避免模型读取对象库。凭据通过 askpass 临时目录注入,
不写入 remote URL、`.git/config`、日志或 prompt。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol, Sequence

from testing_agent_ai_worker.config.models import AgentBackendConfig, UiGenerationConfig
from testing_agent_ai_worker.models.task import GitlabCredentials, RepositoryBinding, Task
from testing_agent_ai_worker.platform.http_client import PlatformHttpClient
from testing_agent_ai_worker.platform.task_source import parse_gitlab_credentials
from testing_agent_ai_worker.tasks.git_workspace import (
    GitRunner,
    GitWorkspaceError,
    SubprocessGitRunner,
    checkout_head,
    clone_repository,
    fetch_commits,
    git_env,
    resolve_credential,
    retain_failed_workspace,
    sweep_expired_workspaces,
    task_run_root,
)

SOURCE_KIND_REPOSITORY = "repository"


class RepositorySourceError(RuntimeError):
    """UI 仓库源码准备失败;消息可直接返回给用户。"""


@dataclass(slots=True)
class RepositorySource:
    """本次 run 的仓库源码根,以及可安全回传的仓库身份。"""

    binding: RepositoryBinding
    run_root: Path
    source_root: Path
    commit: str

    @property
    def metadata(self) -> dict[str, object]:
        return {
            "sourceKind": SOURCE_KIND_REPOSITORY,
            "sourceRepository": {
                "bindingId": self.binding.binding_id,
                "repositoryId": self.binding.repository_id,
                "pathWithNamespace": self.binding.path_with_namespace,
                "branch": self.binding.branch,
                "commit": self.commit,
            },
            "sourceCommit": self.commit,
        }


class RepositorySourcePreparer(Protocol):
    def prepare(
        self, *, task: Task, credentials: Sequence[GitlabCredentials]
    ) -> RepositorySource: ...


@dataclass(slots=True)
class PinnedRepositorySourcePreparer:
    agent_config: AgentBackendConfig
    config: UiGenerationConfig
    runner: GitRunner | None = None
    now: datetime | None = None

    def prepare(self, *, task: Task, credentials: Sequence[GitlabCredentials]) -> RepositorySource:
        return prepare_repository_source(
            task,
            credentials,
            agent_config=self.agent_config,
            config=self.config,
            runner=self.runner,
            now=self.now,
        )


def prepare_repository_source(
    task: Task,
    credentials: Sequence[GitlabCredentials],
    *,
    agent_config: AgentBackendConfig,
    config: UiGenerationConfig,
    runner: GitRunner | None = None,
    now: datetime | None = None,
) -> RepositorySource:
    """Clone the single selected repository at the frozen commit.

    The whole checkout is the source root; failures retain the run workspace for
    diagnosis and the caller removes it after a successful stage.
    """

    binding = _selected_binding(task)
    commit = _pinned_commit(task, binding)
    if not binding.branch:
        raise RepositorySourceError(f"仓库 {binding.repository_id} 缺少工作分支")
    if not binding.clone_url:
        raise RepositorySourceError(f"仓库 {binding.repository_id} 缺少克隆地址")

    credential = resolve_credential(binding, credentials)
    if credential is None:
        raise RepositorySourceError(f"仓库 {binding.repository_id} 未匹配到 GitLab 凭据")

    run_root = task_run_root(agent_config, task)
    sweep_expired_workspaces(agent_config, now=now)
    if run_root.exists():
        shutil.rmtree(run_root, ignore_errors=True)
    source_root = run_root / "source"
    run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (run_root / ".active").write_text("1", encoding="utf-8")

    git = runner or SubprocessGitRunner()
    auth_root = Path(tempfile.mkdtemp(prefix=".git-auth-", dir=run_root))
    try:
        env = git_env(auth_root / "repo-0", credential)
        clone_repository(binding, source_root, env, git, timeout=config.git_timeout_seconds)
        fetch_commits(
            git,
            source_root,
            binding,
            env,
            config.git_timeout_seconds,
            commits=(commit,),
        )
        checkout_head(git, source_root, binding, commit, env, timeout=config.git_timeout_seconds)
        _check_checkout_limits(source_root, config)
        _remove_git_dir(source_root)
        return RepositorySource(
            binding=binding,
            run_root=run_root,
            source_root=source_root,
            commit=commit,
        )
    except GitWorkspaceError as error:
        raise RepositorySourceError(str(error)) from error
    finally:
        shutil.rmtree(auth_root, ignore_errors=True)


def cleanup_repository_source(
    source: RepositorySource,
    *,
    success: bool,
    config: UiGenerationConfig,
) -> None:
    """成功删除工作区;失败保留诊断窗口。"""

    if success:
        shutil.rmtree(source.run_root, ignore_errors=True)
        return
    retain_failed_workspace(source.run_root, config.workspace_retention_hours)


def build_credentials_fetcher(
    client: PlatformHttpClient,
) -> Callable[[Task], list[GitlabCredentials]]:
    """按任务的 gitlabCredentialsUrl 获取本次 UI 发起人的 GitLab 凭据。"""

    def _fetch(task: Task) -> list[GitlabCredentials]:
        url = task.gitlab_credentials_url
        if not url:
            raise RepositorySourceError("快照缺少 gitlabCredentialsUrl")
        payload = client.get(url)
        return parse_gitlab_credentials(payload)

    return _fetch


def _selected_binding(task: Task) -> RepositoryBinding:
    if not task.bindings:
        raise RepositorySourceError("UI 用例生成缺少仓库来源绑定")
    if len(task.bindings) > 1:
        raise RepositorySourceError("UI 用例生成只支持一个仓库来源")
    binding = task.bindings[0]
    repository_id = str(_metadata_dict(task, "sourceRepository").get("repositoryId") or "").strip()
    if repository_id and repository_id != binding.repository_id:
        raise RepositorySourceError("UI 仓库来源与绑定仓库不一致")
    if binding.profile_error:
        raise RepositorySourceError(f"仓库 {binding.repository_id} 不可用: {binding.profile_error}")
    return binding


def _pinned_commit(task: Task, binding: RepositoryBinding) -> str:
    """优先使用冻结的 sourceCommit,回退 sourceRepository.commit 与绑定 headCommit。"""

    candidates = [
        str(task.payload.metadata.get("sourceCommit") or "").strip(),
        str(_metadata_dict(task, "sourceRepository").get("commit") or "").strip(),
        binding.head_commit.strip(),
    ]
    for commit in candidates:
        if commit:
            return commit
    raise RepositorySourceError(f"仓库 {binding.repository_id} 缺少固定 commit")


def _metadata_dict(task: Task, key: str) -> dict[str, object]:
    value = task.payload.metadata.get(key)
    return value if isinstance(value, dict) else {}


def _check_checkout_limits(source_root: Path, config: UiGenerationConfig) -> None:
    """统计工作树大小和文件数;`.git` 不计入,超过限制时保留工作区供排查。"""

    max_bytes = config.max_repo_size_mb * 1024 * 1024
    total_bytes = 0
    file_count = 0
    for root, dirnames, filenames in os.walk(source_root, followlinks=False):
        dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in filenames:
            path = Path(root) / name
            try:
                size = path.lstat().st_size
            except OSError:
                continue
            total_bytes += size
            file_count += 1
            if file_count > config.max_repo_files:
                raise RepositorySourceError(f"仓库文件数超过上限（{config.max_repo_files}）")
            if total_bytes > max_bytes:
                raise RepositorySourceError(f"仓库大小超过上限（{config.max_repo_size_mb:g} MB）")


def _remove_git_dir(source_root: Path) -> None:
    git_dir = source_root / ".git"
    if git_dir.is_dir():
        shutil.rmtree(git_dir)
    elif git_dir.exists():
        git_dir.unlink()


__all__ = [
    "PinnedRepositorySourcePreparer",
    "RepositorySource",
    "RepositorySourceError",
    "RepositorySourcePreparer",
    "SOURCE_KIND_REPOSITORY",
    "build_credentials_fetcher",
    "cleanup_repository_source",
    "prepare_repository_source",
]
