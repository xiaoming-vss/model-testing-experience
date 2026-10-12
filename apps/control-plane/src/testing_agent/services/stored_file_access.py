"""Validate persisted business ownership before exposing an associated file.

Requirement/source replacements and archived Bug evidence retain their owning
resource. Skills instead expose only their published current manifest.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrNotFound
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.bug import Bug
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun
from testing_agent.models.worker_task import WorkerTask


async def require_file_resource(session: AsyncSession, row: StoredFile) -> None:
    if row.status not in {"attached", "archived"}:
        return
    if not row.resource_id:
        raise ErrNotFound()
    if row.resource_type == "requirement" and row.purpose in {"requirement", "attachment"}:
        query = (
            select(Requirement.requirement_id)
            .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
            .where(
                Requirement.requirement_id == row.resource_id, Sprint.project_id == row.project_id
            )
        )
    elif row.resource_type == "bug" and row.purpose == "attachment":
        query = select(Bug.bug_id).where(
            Bug.bug_id == row.resource_id, Bug.project_id == row.project_id
        )
    elif row.resource_type == "ui_source_archive" and row.purpose == "ui_source_archive":
        query = select(AiGenerateTask.task_id).where(
            AiGenerateTask.task_id == row.resource_id,
            AiGenerateTask.project_id == row.project_id,
            AiGenerateTask.task_type == "ui_case_generate",
        )
    elif row.resource_type == "project_skill" and row.purpose == "project_skill":
        skill = await session.scalar(
            select(ProjectSkillSpace)
            .where(ProjectSkillSpace.skill_space_id == row.resource_id)
            .execution_options(populate_existing=True)
        )
        if (
            skill is None
            or (skill.project_id or "") != row.project_id
            or not any(entry.get("fileId") == row.file_id for entry in skill.manifest)
        ):
            raise ErrNotFound()
        return
    elif row.resource_type == "ui_worker_task" and row.purpose == "ui_artifact":
        task = await session.scalar(
            select(WorkerTask)
            .where(WorkerTask.domain == "ui", WorkerTask.task_id == row.resource_id)
            .execution_options(populate_existing=True)
        )
        if task is None:
            raise ErrNotFound()
        if task.task_type == "suite_run":
            query = (
                select(UiTestSuiteRun.suite_run_id)
                .join(UiTestSuite, UiTestSuite.suite_id == UiTestSuiteRun.suite_id)
                .where(UiTestSuiteRun.suite_run_id == task.run_id)
            )
        elif task.task_type == "case_debug":
            query = (
                select(UiTestCaseRun.run_id)
                .join(UiTestCase, UiTestCase.case_id == UiTestCaseRun.case_id)
                .join(UiTestSuite, UiTestSuite.suite_id == UiTestCase.suite_id)
                .where(
                    UiTestCaseRun.run_id == task.run_id,
                    UiTestCaseRun.suite_id == UiTestCase.suite_id,
                )
            )
        else:
            raise ErrNotFound()
        query = (
            query.join(Requirement, Requirement.requirement_id == UiTestSuite.requirement_id)
            .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
            .where(Sprint.project_id == row.project_id)
        )
    else:
        # New resource kinds must define their ownership rules explicitly.
        raise ErrNotFound()
    if await session.scalar(query) is None:
        raise ErrNotFound()
