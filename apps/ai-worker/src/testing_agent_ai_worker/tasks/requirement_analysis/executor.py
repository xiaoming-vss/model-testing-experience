"""Requirement analysis executor: extraction review, then understanding."""

from datetime import datetime

from testing_agent_ai_worker.config.models import NanobotConfig
from testing_agent_ai_worker.models.execution import TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.nanobot_runtime.config_builder import task_config_path
from testing_agent_ai_worker.nanobot_runtime.paths import (
    resolve_runtime_paths,
    resolve_task_workspace,
)
from testing_agent_ai_worker.tasks.requirement_analysis.skill import run_skill_step
from testing_agent_ai_worker.tasks.requirement_analysis.source_downloader import (
    RequirementSourceDownloader,
)
from testing_agent_ai_worker.tasks.requirement_analysis.two_stage import execute_two_stage
from testing_agent_ai_worker.worker.runner import TaskExecutor

REQUIREMENT_ANALYSIS_FIRST_SKILL_NAME = "extract-docx-enhanced-text"
REQUIREMENT_ANALYSIS_SECOND_SKILL_NAME = "prd-feature-understanding-skill"
SUPPORTED_REQUIREMENT_ANALYSIS_DOCUMENT_TYPES = {"text", "word"}


def normalize_requirement_analysis_document_type(document_type: str) -> str:
    normalized = document_type.strip().lower()
    return {"docx": "word", "txt": "text"}.get(normalized, normalized)


class RequirementAnalysisNanobotExecutor(TaskExecutor):
    def __init__(
        self,
        *,
        nanobot_config: NanobotConfig,
        skill_runner=run_skill_step,
        first_skill_name: str = REQUIREMENT_ANALYSIS_FIRST_SKILL_NAME,
        second_skill_name: str = REQUIREMENT_ANALYSIS_SECOND_SKILL_NAME,
        source_downloader: RequirementSourceDownloader | None = None,
    ) -> None:
        self.nanobot_config = nanobot_config
        self.runtime_paths = resolve_runtime_paths(nanobot_config)
        self.skill_runner = skill_runner
        self.first_skill_name = first_skill_name
        self.second_skill_name = second_skill_name
        self.source_downloader = source_downloader

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult | None:
        if task.task_type != "requirement_analysis":
            return TaskResult(
                task_id=task.task_id,
                run_id=task.run_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.FAILED,
                error_message=f"不支持的任务类型: {task.task_type}",
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
            )
        task.payload.document_type = normalize_requirement_analysis_document_type(
            task.payload.document_type
        )
        if task.payload.document_type not in SUPPORTED_REQUIREMENT_ANALYSIS_DOCUMENT_TYPES:
            return TaskResult(
                task_id=task.task_id,
                run_id=task.run_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.FAILED,
                error_message=f"不支持的 document_type: {task.payload.document_type}",
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
            )
        workspace = resolve_task_workspace(self.nanobot_config, task)
        with task_config_path(nanobot_config=self.nanobot_config, task=task) as config_path:
            return execute_two_stage(
                task=task,
                started_at=started_at,
                progress_callback=progress_callback,
                config_path=config_path,
                workspace=workspace,
                skill_runner=self.skill_runner,
                source_downloader=self.source_downloader,
                first_skill_name=self.first_skill_name,
                second_skill_name=self.second_skill_name,
            )
