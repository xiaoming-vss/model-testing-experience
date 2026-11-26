"""Requirement analysis executor: material organization and review."""

from datetime import datetime

from testing_agent_ai_worker.agent.config_builder import task_config_path
from testing_agent_ai_worker.agent.paths import resolve_task_workspace
from testing_agent_ai_worker.config.models import AgentBackendConfig
from testing_agent_ai_worker.models.execution import TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.skill_names import (
    MATERIAL_SKILL,
)
from testing_agent_ai_worker.tasks.requirement_analysis.document_type import extraction_skill
from testing_agent_ai_worker.tasks.requirement_analysis.history_stage import execute_history_stage
from testing_agent_ai_worker.tasks.requirement_analysis.history_verification_stage import (
    execute_history_verification_stage,
)
from testing_agent_ai_worker.tasks.requirement_analysis.material_stage import execute_material_stage
from testing_agent_ai_worker.tasks.requirement_analysis.review_stage import (
    execute_review_stage,
)
from testing_agent_ai_worker.tasks.requirement_analysis.skill import run_skill_step
from testing_agent_ai_worker.tasks.requirement_analysis.source_downloader import (
    RequirementSourceDownloader,
)
from testing_agent_ai_worker.worker.runner import TaskExecutor

REQUIREMENT_ANALYSIS_FIRST_SKILL_NAME = MATERIAL_SKILL
SUPPORTED_REQUIREMENT_ANALYSIS_DOCUMENT_TYPES = {"word", "richtext"}


def normalize_requirement_analysis_document_type(document_type: str) -> str:
    normalized = document_type.strip().lower()
    return {"docx": "word"}.get(normalized, normalized)


class RequirementAnalysisExecutor(TaskExecutor):
    def __init__(
        self,
        *,
        agent_config: AgentBackendConfig,
        skill_runner=run_skill_step,
        first_skill_name: str = REQUIREMENT_ANALYSIS_FIRST_SKILL_NAME,
        source_downloader: RequirementSourceDownloader | None = None,
        attachment_downloader=None,
    ) -> None:
        self.agent_config = agent_config
        self.skill_runner = skill_runner
        self.first_skill_name = first_skill_name
        self.source_downloader = source_downloader
        self.attachment_downloader = attachment_downloader

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult | None:
        if task.task_type != "requirement_analysis":
            return TaskResult(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.FAILED,
                error_message=f"不支持的任务类型: {task.task_type}",
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
            )
        stage = task.current_stage or "extracting_text"
        if stage == "historical_test_case_verification":
            with task_config_path(agent_config=self.agent_config, task=task) as config_path:
                return execute_history_verification_stage(
                    task=task,
                    started_at=started_at,
                    config_path=config_path,
                    workspace=resolve_task_workspace(self.agent_config, task),
                    progress_callback=progress_callback,
                    skill_runner=self.skill_runner,
                    attachment_downloader=self.attachment_downloader,
                )
        if stage == "historical_requirement_relations":
            with task_config_path(agent_config=self.agent_config, task=task) as config_path:
                return execute_history_stage(
                    task=task,
                    started_at=started_at,
                    config_path=config_path,
                    workspace=resolve_task_workspace(self.agent_config, task),
                    skill_runner=self.skill_runner,
                    attachment_downloader=self.attachment_downloader,
                )
        task.payload.document_type = normalize_requirement_analysis_document_type(
            task.payload.document_type
        )
        if task.payload.document_type not in SUPPORTED_REQUIREMENT_ANALYSIS_DOCUMENT_TYPES:
            return TaskResult(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.FAILED,
                error_message=f"不支持的 document_type: {task.payload.document_type}",
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
            )
        workspace = resolve_task_workspace(self.agent_config, task)
        with task_config_path(agent_config=self.agent_config, task=task) as config_path:
            if stage == "requirement_review":
                return execute_review_stage(
                    task=task,
                    started_at=started_at,
                    progress_callback=progress_callback,
                    config_path=config_path,
                    workspace=workspace,
                    skill_runner=self.skill_runner,
                    source_downloader=self.source_downloader,
                    attachment_downloader=self.attachment_downloader,
                )
            if stage == "extracting_text":
                return execute_material_stage(
                    task=task,
                    started_at=started_at,
                    progress_callback=progress_callback,
                    config_path=config_path,
                    workspace=workspace,
                    skill_runner=self.skill_runner,
                    source_downloader=self.source_downloader,
                    attachment_downloader=self.attachment_downloader,
                    first_skill_name=extraction_skill(task.payload.document_type),
                )
            raise ValueError(f"需求分析不支持阶段: {stage}")
