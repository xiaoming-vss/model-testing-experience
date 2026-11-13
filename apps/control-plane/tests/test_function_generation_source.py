from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from support.generation import generation_services

from testing_agent.core.errors import AppError
from testing_agent.services.ai_task_output import (
    build_generate_run_snapshot as _generation_build_generate_run_snapshot,
)


@pytest.mark.asyncio
async def test_legacy_linked_function_launch_is_rejected_without_creating_tasks(
    monkeypatch,
):
    repository = SimpleNamespace(
        session=AsyncMock(),
        get_project=AsyncMock(
            return_value=SimpleNamespace(project_id="project-1", user_id="user-1")
        ),
        add_all=Mock(),
        commit=AsyncMock(),
    )
    service = generation_services(repository)
    service.access.owned_task = AsyncMock(
        return_value=SimpleNamespace(
            requirement_id="requirement-1", project_id="project-1", source_content="original text"
        )
    )
    monkeypatch.setattr(
        "testing_agent.services.ai_run_launcher.require_personal_connection", AsyncMock()
    )
    with pytest.raises(AppError, match="请在需求生成链") as error:
        await service.launcher.launch("function", "task-1", {"connectionId": "mine"}, "user-1")
    assert error.value.http_code == 400
    repository.add_all.assert_not_called()
    repository.commit.assert_not_called()


@pytest.mark.parametrize("kind", ["requirement_analysis", "function", "api", "ui"])
async def test_requirement_generation_cannot_bypass_independent_stages(kind, monkeypatch):
    repository = SimpleNamespace(
        session=AsyncMock(),
        get_project=AsyncMock(
            return_value=SimpleNamespace(project_id="project-1", user_id="user-1")
        ),
        add_all=Mock(),
        commit=AsyncMock(),
    )
    bundle = generation_services(repository)
    bundle.access.owned_task = AsyncMock(
        return_value=SimpleNamespace(requirement_id="requirement-1", project_id="project-1")
    )
    monkeypatch.setattr(
        "testing_agent.services.ai_run_launcher.require_project_access", AsyncMock()
    )
    with pytest.raises(AppError, match="请在需求生成链"):
        await bundle.launcher.launch(kind, "task-1", {"connectionId": "mine"}, "user-1")
    repository.add_all.assert_not_called()
    repository.commit.assert_not_called()


@pytest.mark.asyncio
async def test_function_snapshot_rejects_missing_requirement_understanding():
    repository = SimpleNamespace(session=AsyncMock())
    task = SimpleNamespace(requirement_id="requirement-1", source_content="legacy task source")
    with pytest.raises(AppError, match="请先审核通过材料整理，再生成功能用例"):
        await _generation_build_generate_run_snapshot(repository, "function", task, "run-1")
