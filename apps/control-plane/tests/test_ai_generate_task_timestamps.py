from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase

from testing_agent.services.ai_generate_task import AiGenerateTaskService, dump_task

CREATED_AT = datetime(2026, 8, 4, 1, 2, 3, tzinfo=UTC)
UPDATED_AT = datetime(2026, 8, 5, 4, 5, 6, tzinfo=UTC)


def make_task(task_type: str = "api_case_generate") -> SimpleNamespace:
    return SimpleNamespace(
        task_id="task-1",
        task_type=task_type,
        name="Generate cases",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        creator_user_id="user-1",
        source_type="manual",
        source_content="requirements",
        instruction="cover edge cases",
        created_at=CREATED_AT,
        updated_at=UPDATED_AT,
    )


def test_dump_task_includes_creation_and_modification_times():
    payload = dump_task(make_task())

    assert payload["createdAt"] == CREATED_AT
    assert payload["updatedAt"] == UPDATED_AT


class TaskQueryRepository:
    session = AuthorizationDatabase()

    def __init__(self, task):
        self.task = task

    async def get_project(self, project_id):
        if project_id == self.task.project_id:
            return SimpleNamespace(project_id=project_id, user_id="user-1")
        return None

    async def get_task(self, task_id):
        return self.task if task_id == self.task.task_id else None

    async def list_tasks(self, project_id, task_type):
        if project_id == self.task.project_id and task_type == self.task.task_type:
            return [self.task]
        return []

    async def get_source_archive(self, _task_id):
        return None


@pytest.mark.parametrize(
    ("kind", "task_type"),
    [
        ("api", "api_case_generate"),
        ("function", "functional_case_generate"),
        ("ui", "ui_case_generate"),
        ("requirement_analysis", "requirement_analysis"),
    ],
)
async def test_task_list_and_detail_queries_include_timestamps(kind, task_type):
    task = make_task(task_type)
    service = AiGenerateTaskService(TaskQueryRepository(task))

    listed = await service.list(kind, "project-1", "user-1")
    detail = await service.get(kind, "task-1", "user-1")

    assert listed["items"][0]["createdAt"] == CREATED_AT
    assert listed["items"][0]["updatedAt"] == UPDATED_AT
    assert detail["createdAt"] == CREATED_AT
    assert detail["updatedAt"] == UPDATED_AT
