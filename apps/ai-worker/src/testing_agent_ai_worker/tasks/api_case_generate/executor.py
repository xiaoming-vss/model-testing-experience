"""API test case generation executor."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from testing_agent_ai_worker.agent.config_builder import task_config_path
from testing_agent_ai_worker.agent.paths import (
    resolve_runtime_paths,
    resolve_task_workspace,
)
from testing_agent_ai_worker.config.models import AgentBackendConfig
from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.platform.revision_attachments import parse_revision_attachments
from testing_agent_ai_worker.tasks.api_case_generate.chain import (
    ChainRunResult,
    run_api_stage,
    run_chain,
)
from testing_agent_ai_worker.tasks.api_case_generate.contracts import (
    validate_cases,
    validate_extraction,
)
from testing_agent_ai_worker.tasks.result_summary import build_task_result_summary
from testing_agent_ai_worker.worker.runner import TaskExecutor


def _resolve_runner_result(result):
    """兼容同步假实现和真实异步 nanobot 调用。"""

    if hasattr(result, "__await__"):
        return asyncio.run(result)
    return result


class ApiCaseExecutor(TaskExecutor):
    """API 用例生成执行器。"""

    def __init__(
        self,
        *,
        agent_config: AgentBackendConfig,
        chain_runner=run_chain,
        stage_runner=run_api_stage,
        attachment_downloader=None,
    ) -> None:
        self.agent_config = agent_config
        self.runtime_paths = resolve_runtime_paths(agent_config)
        self.chain_runner = chain_runner
        self.stage_runner = stage_runner
        self.attachment_downloader = attachment_downloader

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult | None:
        """执行 API 用例生成。"""

        if task.task_type != "api_case_generate":
            return TaskResult(
                task_id=task.task_id,
                run_id=task.run_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.FAILED,
                error_message=f"不支持的任务类型: {task.task_type}",
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
            )

        workspace = resolve_task_workspace(self.agent_config, task)
        if task.payload.metadata.get("apiWorkflowVersion") == "api_two_stage/1.0":
            return self._execute_stage(task, started_at, progress_callback, workspace)

        with task_config_path(agent_config=self.agent_config, task=task) as config_path:
            result = self.chain_runner(
                openapi_text=task.payload.openapi_content,
                session_key=task.session_key,
                extractor_skill_name="openapi-test-config-extractor",
                generator_skill_name="api-cases-yaml-generator",
                config_path=config_path,
                workspace=str(workspace),
                extra_instruction=self._build_api_instruction(task),
                on_validation_progress=lambda event, extracted: progress_callback(
                    TaskProgress(
                        task_id=task.task_id,
                        run_id=task.run_id,
                        current_stage=event["stage"],
                        stage_status="running",
                        intermediate_json_text=extracted or task.config_json,
                        result_summary_json=json.dumps(
                            {"outputValidation": event}, ensure_ascii=False
                        ),
                    )
                ),
                on_extractor_result=lambda extractor_output: progress_callback(
                    self._build_progress(task, extractor_output)
                ),
            )
            chain_result = _resolve_runner_result(result)
        assert isinstance(chain_result, ChainRunResult)
        validate_extraction(chain_result.extractor_output)
        validate_cases(chain_result.generator_output)

        return TaskResult(
            task_id=task.task_id,
            run_id=task.run_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.SUCCESS,
            intermediate_json_text=chain_result.extractor_output,
            output_yaml=chain_result.generator_output,
            result_summary_json=self._build_result_summary_json(
                task,
                TaskStatus.SUCCESS,
                chain_result.extractor_output,
                chain_result.generator_output,
                None,
            ),
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )

    def _execute_stage(self, task: Task, started_at: datetime, progress_callback, workspace):
        if not task.checkpoint_enabled or task.current_stage not in {"openapi_extract", "generate"}:
            raise ValueError("API 两阶段生成需要有效阶段及人工审核")
        config = json.loads(task.config_json or "{}")
        if not isinstance(config, dict):
            raise ValueError("configJson 必须是对象")
        stage = task.current_stage
        if stage == "openapi_extract":
            source = task.payload.openapi_content
        else:
            extracted = config.get("apiExtraction")
            if extracted is None:
                raise ValueError("缺少已审核的接口配置")
            source = (
                extracted
                if isinstance(extracted, str)
                else json.dumps(extracted, ensure_ascii=False)
            )
            validate_extraction(source)
        instruction = self._build_api_instruction(task)
        revision = str(config.get("revisionInstruction") or "").strip()
        if revision:
            current = config.get("apiExtraction" if stage == "openapi_extract" else "resultYaml")
            if current is None:
                raise ValueError("继续优化缺少当前阶段产物")
            current_text = (
                current if isinstance(current, str) else json.dumps(current, ensure_ascii=False)
            )
            instruction += f"\n当前阶段产物：\n{current_text}\n优化要求：\n{revision}"
        media = []
        attachments = parse_revision_attachments(config) if revision else []
        if attachments:
            if self.attachment_downloader is None:
                raise ValueError("未配置继续优化图片下载器")
            images = self.attachment_downloader.download(
                task_id=task.task_id, workspace=workspace, attachments=attachments
            )
            media = [image["sourcePath"] for image in images]
        with task_config_path(agent_config=self.agent_config, task=task) as config_path:
            output = _resolve_runner_result(
                self.stage_runner(
                    stage=stage,
                    input_text=source,
                    session_key=task.session_key,
                    config_path=config_path,
                    workspace=str(workspace),
                    extra_instruction=instruction,
                    media=media,
                    on_validation_progress=lambda event: progress_callback(
                        TaskProgress(
                            task_id=task.task_id,
                            run_id=task.run_id,
                            current_stage=stage,
                            stage_status="running",
                            intermediate_json_text=json.dumps(config, ensure_ascii=False),
                            result_summary_json=json.dumps({"outputValidation": event}),
                        )
                    ),
                )
            )
        if stage == "openapi_extract":
            validate_extraction(output)
            progress_callback(
                TaskProgress(
                    task_id=task.task_id,
                    run_id=task.run_id,
                    current_stage=stage,
                    stage_status="waiting_review",
                    intermediate_json_text=json.dumps(
                        {"apiExtraction": json.loads(output)}, ensure_ascii=False
                    ),
                )
            )
            return None
        validate_cases(output)
        return TaskResult(
            task_id=task.task_id,
            run_id=task.run_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.SUCCESS,
            intermediate_json_text=json.dumps({"apiExtraction": extracted}, ensure_ascii=False),
            output_yaml=output,
            result_summary_json=self._build_result_summary_json(
                task, TaskStatus.SUCCESS, source, output, None
            ),
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )

    def _build_progress(self, task: Task, extractor_output: str) -> TaskProgress:
        validate_extraction(extractor_output)
        return TaskProgress(
            task_id=task.task_id,
            run_id=task.run_id,
            current_stage="openapi_extract",
            stage_status="running",
            intermediate_json_text=extractor_output,
            result_summary_json=self._build_result_summary_json(
                task,
                "running",
                extractor_output,
                "",
                None,
            ),
        )

    def _build_result_summary_json(
        self,
        task: Task,
        status: TaskStatus | str,
        intermediate_json_text: str,
        output_yaml: str,
        error_message: str | None,
    ) -> str:
        return build_task_result_summary(
            task=task,
            status=status,
            error_message=error_message,
            details={
                "sourceType": task.payload.source_type,
                "jsonLength": len(intermediate_json_text),
                "yamlLength": len(output_yaml),
            },
        )

    @staticmethod
    def _build_api_instruction(task: Task) -> str:
        parts: list[str] = []
        if task.payload.target_scope.strip():
            parts.append(task.payload.target_scope.strip())
        if task.payload.extra_instruction.strip():
            parts.append(task.payload.extra_instruction.strip())
        return "\n".join(parts)
