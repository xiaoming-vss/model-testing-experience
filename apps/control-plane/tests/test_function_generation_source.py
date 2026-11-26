from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from support.generation import generation_services

from testing_agent.core.errors import AppError


@pytest.mark.parametrize("kind", ["requirement_analysis", "function", "api", "ui"])
async def test_independent_stage_launch_is_rejected_without_creating_tasks(kind):
    repository = SimpleNamespace(
        session=AsyncMock(),
        get_project=AsyncMock(
            return_value=SimpleNamespace(project_id="project-1", user_id="user-1")
        ),
        add_all=Mock(),
        commit=AsyncMock(),
    )
    bundle = generation_services(repository)

    with pytest.raises(AppError) as error:
        await bundle.launcher.launch(kind, "task-1", {"connectionId": "mine"}, "user-1")

    assert error.value.http_code == 400
    repository.add_all.assert_not_called()
    repository.commit.assert_not_called()
