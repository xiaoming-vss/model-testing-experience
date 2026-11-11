"""Code risk analysis executor: code workspace, context package and preview call."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable

import yaml

from testing_agent_ai_worker.agent.config_builder import task_config_path
from testing_agent_ai_worker.agent.prompt_step import run_agent_prompt
from testing_agent_ai_worker.config.models import (
    AgentBackendConfig,
    CodeRiskAnalysisConfig,
    PiConfig,
)
from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import GitlabCredentials, Task
from testing_agent_ai_worker.platform.http_client import PlatformHttpClient
from testing_agent_ai_worker.platform.task_source import parse_gitlab_credentials
from testing_agent_ai_worker.tasks.code_risk_analysis.context import (
    ContextPackage,
    build_code_context,
)
from testing_agent_ai_worker.tasks.code_risk_analysis.preview_prompt import ContextReceiptError
from testing_agent_ai_worker.tasks.code_risk_analysis.report_prompt import build_report_prompt
from testing_agent_ai_worker.tasks.code_risk_analysis.report_validation import (
    RiskReportValidationError,
    validate_risk_report,
)
from testing_agent_ai_worker.tasks.code_risk_analysis.workspace import (
    CodeWorkspace,
    CodeWorkspaceError,
    cleanup_code_workspace,
    code_run_root,
    prepare_code_workspace,
    retain_failed_workspace,
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


class CodeRiskAnalysisExecutor(TaskExecutor):
    """Pull pinned code into a per-run workspace and run the preview agent."""

    def __init__(
        self,
        *,
        agent_config: AgentBackendConfig,
        code_risk_config: CodeRiskAnalysisConfig | None = None,
        credentials_fetcher: Callable[[Task], list[GitlabCredentials]] | None = None,
        workspace_preparer: Callable[..., CodeWorkspace] | None = None,
        context_builder: Callable[..., ContextPackage] | None = None,
        prompt_runner: Callable[..., Any] | None = None,
        client: PlatformHttpClient | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.agent_config = agent_config
        self.code_risk_config = code_risk_config or CodeRiskAnalysisConfig()
        self.credentials_fetcher = credentials_fetcher or (
            _platform_credentials_fetcher(client) if client is not None else None
        )
        self.workspace_preparer = workspace_preparer or prepare_code_workspace
        self.context_builder = context_builder or build_code_context
        self.prompt_runner = prompt_runner or run_agent_prompt
        self.timeout_seconds = timeout_seconds

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult:
        if task.task_type != "code_risk_analysis":
            return self._failed_result(task, started_at, f"不支持的任务类型: {task.task_type}")
        if not isinstance(self.agent_config, PiConfig):
            return self._failed_result(
                task,
                started_at,
                "本期代码风险预览仅支持 Pi 后端",
            )

        requirement = task.requirement_input
        if requirement is None or not requirement.document_content.strip():
            return self._failed_result(
                task,
                started_at,
                "该需求尚未完成需求分析(快照缺少需求理解记录)",
            )
        if self.credentials_fetcher is None:
            return self._failed_result(task, started_at, "worker 未配置 GitLab 凭据获取")
        try:
            credentials = self.credentials_fetcher(task)
        except Exception as exc:
            return self._failed_result(task, started_at, f"GitLab 凭据不可用: {exc}")

        run_root = code_run_root(self.agent_config, task)
        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                current_stage="fetching_diff",
                stage_status="running",
            )
        )
        prepared: CodeWorkspace | None = None
        try:
            prepared = self.workspace_preparer(
                task,
                credentials,
                agent_config=self.agent_config,
                config=self.code_risk_config,
            )
            context = self.context_builder(
                task,
                prepared,
                max_diff_chars=self.code_risk_config.max_diff_chars,
            )
            progress_callback(
                TaskProgress(
                    task_id=task.task_id,
                    attempt_id=task.attempt_id,
                    current_stage="analyzing",
                    stage_status="running",
                )
            )
            with task_config_path(agent_config=self.agent_config, task=task) as config_path:
                expected_case_ids = {
                    case.case_id
                    for cases in (
                        task.existing_tests.function_cases,
                        task.existing_tests.api_cases,
                        task.existing_tests.ui_cases,
                    )
                    for case in cases
                    if case.case_id
                }
                raw_output = ""
                report = None
                errors = None
                for attempt in range(3):
                    progress_callback(
                        TaskProgress(
                            task_id=task.task_id,
                            attempt_id=task.attempt_id,
                            current_stage="analyzing",
                            stage_status="repairing" if attempt else "running",
                            result_summary_json=json.dumps(
                                {"outputValidation": {"repairAttempt": attempt, "maxRepairs": 2}},
                                ensure_ascii=False,
                            ),
                        )
                    )
                    raw_output = self._resolve_runner_result(
                        self.prompt_runner(
                            input_text=build_report_prompt(
                                context,
                                prepared,
                                previous_output=raw_output if errors else "",
                                errors=errors,
                            ),
                            session_key=task.session_key,
                            config_path=config_path,
                            workspace=str(prepared.code_root),
                            tools=READ_ONLY_TOOLS,
                        )
                    )
                    try:
                        report = validate_risk_report(
                            raw_output,
                            prepared,
                            expected_case_ids=expected_case_ids,
                        )
                        break
                    except RiskReportValidationError as exc:
                        errors = exc.issues
                        if attempt == 2:
                            raise
                if report is None:
                    raise RiskReportValidationError(errors or [])
            receipt = {
                "analyzedAt": datetime.now().astimezone().isoformat(),
                "repositories": prepared.manifest["repositories"],
                **report,
            }
            output_yaml = yaml.safe_dump(receipt, allow_unicode=True, sort_keys=False)
            result_summary = build_task_result_summary(
                task=task,
                status=TaskStatus.SUCCESS,
                error_message=None,
                details={
                    "repositoryCount": len(prepared.repositories),
                    "filesChangedTotal": sum(repo.files_changed for repo in prepared.repositories),
                    "diffChars": context.diff_chars,
                    "truncatedFiles": len(context.truncated_files),
                },
            )
            cleanup_code_workspace(
                prepared,
                success=True,
                config=self.code_risk_config,
            )
            return TaskResult(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.SUCCESS,
                output_yaml=output_yaml,
                result_summary_json=result_summary,
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
            )
        except Exception as exc:
            if isinstance(
                exc, (CodeWorkspaceError, ContextReceiptError, RiskReportValidationError)
            ):
                LOGGER.warning(
                    "code risk context failed: task_id=%s attempt_id=%s error=%s",
                    task.task_id,
                    task.attempt_id,
                    exc,
                )
            else:
                # 不把提示词、凭据或仓库正文写入日志;堆栈仅用于未知异常定位。
                LOGGER.exception(
                    "code risk analysis failed: task_id=%s attempt_id=%s",
                    task.task_id,
                    task.attempt_id,
                )
            # 保留工作区是诊断辅助;清理标记写入失败不能覆盖原始任务错误。
            try:
                if prepared is not None:
                    cleanup_code_workspace(
                        prepared,
                        success=False,
                        config=self.code_risk_config,
                    )
                else:
                    retain_failed_workspace(
                        run_root,
                        self.code_risk_config.workspace_retention_hours,
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
            raise ValueError("代码上下文预览结果必须是文本")
        return resolved

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, (CodeWorkspaceError, ContextReceiptError, RiskReportValidationError)):
            return str(exc)
        return "代码上下文准备或模型调用失败"

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


__all__ = ["CodeRiskAnalysisExecutor", "READ_ONLY_TOOLS"]
