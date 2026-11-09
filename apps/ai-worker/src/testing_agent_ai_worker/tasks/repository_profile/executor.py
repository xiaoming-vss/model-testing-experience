"""Execute a manual repository profile run with a read-only Pi agent."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable

from testing_agent_ai_worker.agent.config_builder import task_config_path
from testing_agent_ai_worker.agent.prompt_step import run_agent_prompt
from testing_agent_ai_worker.config.models import (
    AgentBackendConfig,
    PiConfig,
    RepositoryProfileConfig,
)
from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import GitlabCredentials, Task
from testing_agent_ai_worker.platform.http_client import PlatformHttpClient
from testing_agent_ai_worker.platform.task_source import parse_gitlab_credentials
from testing_agent_ai_worker.tasks.git_workspace import retain_failed_workspace, task_run_root
from testing_agent_ai_worker.tasks.repository_profile.context import (
    ProfileContext,
    build_profile_context,
)
from testing_agent_ai_worker.tasks.repository_profile.contracts import (
    ProfileContractError,
    canonical_profile_json,
    validate_profile_output,
)
from testing_agent_ai_worker.tasks.repository_profile.prompt import build_profile_prompt
from testing_agent_ai_worker.tasks.repository_profile.workspace import (
    ProfileWorkspace,
    ProfileWorkspaceError,
    cleanup_profile_workspace,
    prepare_profile_workspace,
)
from testing_agent_ai_worker.tasks.result_summary import build_task_result_summary
from testing_agent_ai_worker.worker.runner import TaskExecutor

READ_ONLY_TOOLS = ("read", "grep", "find", "ls")
LOGGER = logging.getLogger("testing_agent_ai_worker")


def _platform_credentials_fetcher(client: PlatformHttpClient):
    def _fetch(task: Task) -> list[GitlabCredentials]:
        url = task.gitlab_credentials_url
        if not url:
            raise RuntimeError("快照缺少 gitlabCredentialsUrl")
        payload = client.get(url)
        return parse_gitlab_credentials(payload)

    return _fetch


class RepositoryProfileExecutor(TaskExecutor):
    """Checkout working-branch HEADs and produce a coarse repository profile."""

    def __init__(
        self,
        *,
        agent_config: AgentBackendConfig,
        profile_config: RepositoryProfileConfig | None = None,
        credentials_fetcher: Callable[[Task], list[GitlabCredentials]] | None = None,
        workspace_preparer: Callable[..., ProfileWorkspace] | None = None,
        context_builder: Callable[..., ProfileContext] | None = None,
        prompt_builder: Callable[..., str] | None = None,
        prompt_runner: Callable[..., Any] | None = None,
        client: PlatformHttpClient | None = None,
    ) -> None:
        self.agent_config = agent_config
        self.profile_config = profile_config or RepositoryProfileConfig()
        self.credentials_fetcher = credentials_fetcher or (
            _platform_credentials_fetcher(client) if client is not None else None
        )
        self.workspace_preparer = workspace_preparer or prepare_profile_workspace
        self.context_builder = context_builder or build_profile_context
        self.prompt_builder = prompt_builder or build_profile_prompt
        self.prompt_runner = prompt_runner or run_agent_prompt

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        if task.task_type != "repository_profile":
            return self._failed_result(task, started_at, f"不支持的任务类型: {task.task_type}")
        if not isinstance(self.agent_config, PiConfig):
            return self._failed_result(task, started_at, "本期仓库画像仅支持 Pi 后端")

        requirement = task.requirement_input
        if requirement is None or not requirement.document_content.strip():
            return self._failed_result(
                task,
                started_at,
                "该需求尚未完成需求分析(快照缺少已审核需求理解记录)",
            )
        if not task.bindings:
            return self._failed_result(task, started_at, "需求未绑定代码仓库，无法生成仓库画像")
        analyzable = [
            binding
            for binding in task.bindings
            if not binding.profile_error and binding.clone_url and binding.head_commit
        ]
        if not analyzable:
            return self._failed_result(
                task,
                started_at,
                "所有绑定仓库均无法读取，无法生成仓库画像",
            )
        if self.credentials_fetcher is None:
            return self._failed_result(task, started_at, "worker 未配置 GitLab 凭据获取")
        try:
            credentials = self.credentials_fetcher(task)
        except Exception:
            return self._failed_result(
                task,
                started_at,
                "GitLab 凭据不可用，请检查个人授权后重试",
            )

        run_root = task_run_root(self.agent_config, task)
        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                current_stage="preparing_workspace",
                stage_status="running",
            )
        )
        prepared: ProfileWorkspace | None = None
        try:
            prepared = self.workspace_preparer(
                task,
                credentials,
                agent_config=self.agent_config,
                config=self.profile_config,
            )
            context = self.context_builder(task, prepared)
            progress_callback(
                TaskProgress(
                    task_id=task.task_id,
                    attempt_id=task.attempt_id,
                    current_stage="profiling",
                    stage_status="running",
                )
            )
            prompt = self.prompt_builder(context, prepared)
            with task_config_path(agent_config=self.agent_config, task=task) as config_path:
                raw_output = self._resolve_runner_result(
                    self.prompt_runner(
                        input_text=prompt,
                        session_key=task.session_key,
                        config_path=config_path,
                        workspace=str(prepared.code_root),
                        tools=READ_ONLY_TOOLS,
                    )
                )
            profile = validate_profile_output(
                raw_output,
                prepared,
                max_output_chars=self.profile_config.max_output_chars,
            )
            result_summary = build_task_result_summary(
                task=task,
                status=TaskStatus.SUCCESS,
                error_message=None,
                details={
                    "repositoryCount": len(profile["repositories"]),
                    "readableRepositoryCount": len(prepared.repositories),
                    "unknownRepositoryCount": sum(
                        1 for item in profile["repositories"] if item["role"] == "unknown"
                    ),
                },
            )
            cleanup_profile_workspace(
                prepared,
                success=True,
                config=self.profile_config,
            )
            return TaskResult(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.SUCCESS,
                output_yaml=canonical_profile_json(profile),
                result_summary_json=result_summary,
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
            )
        except Exception as exc:
            if isinstance(exc, (ProfileWorkspaceError, ProfileContractError)):
                LOGGER.warning(
                    "repository profile failed: task_id=%s attempt_id=%s error=%s",
                    task.task_id,
                    task.attempt_id,
                    exc,
                )
            else:
                LOGGER.exception(
                    "repository profile failed: task_id=%s attempt_id=%s",
                    task.task_id,
                    task.attempt_id,
                )
            try:
                if prepared is not None:
                    cleanup_profile_workspace(
                        prepared,
                        success=False,
                        config=self.profile_config,
                    )
                else:
                    retain_failed_workspace(
                        run_root,
                        self.profile_config.workspace_retention_hours,
                    )
            except OSError:
                pass
            return self._failed_result(task, started_at, self._safe_error(exc))

    @staticmethod
    def _resolve_runner_result(result: Any) -> str:
        if hasattr(result, "__await__"):
            resolved = asyncio.run(result)
        else:
            resolved = result
        if hasattr(resolved, "content"):
            resolved = resolved.content
        if not isinstance(resolved, str):
            raise ValueError("仓库画像结果必须是文本")
        return resolved

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, (ProfileWorkspaceError, ProfileContractError)):
            return str(exc)
        return "仓库画像准备或模型调用失败"

    def _failed_result(self, task: Task, started_at: datetime, message: str) -> TaskResult:
        return TaskResult(
            task_id=task.task_id,
            attempt_id=task.attempt_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.FAILED,
            error_message=message,
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )


__all__ = ["READ_ONLY_TOOLS", "RepositoryProfileExecutor"]
