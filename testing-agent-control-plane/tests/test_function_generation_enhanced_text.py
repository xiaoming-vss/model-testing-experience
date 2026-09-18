from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from testing_agent.core.errors import AppError
from testing_agent.services import ai_generate_task as ai_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [None, "", " \n\t "])
@pytest.mark.parametrize("document_type", ["text", "docx"])
async def test_function_run_rejects_missing_enhanced_text_without_creating_tasks(
    monkeypatch, content, document_type
):
    repository = SimpleNamespace(
        session=Mock(),
        get_requirement=AsyncMock(return_value=SimpleNamespace(
            document_content=content,
            document_type=document_type,
            document_download_url="/original.docx",
        )),
        add_all=Mock(),
        commit=AsyncMock(),
    )
    service = ai_tasks.AiGenerateTaskService(repository)
    service.owned_task = AsyncMock(return_value=SimpleNamespace(
        requirement_id="requirement-1", project_id="project-1", source_content="original text"
    ))
    monkeypatch.setattr(ai_tasks, "require_personal_connection", AsyncMock())
    with pytest.raises(AppError, match="请先完成需求分析并导入增强文本") as error:
        await service.run("function", "task-1", {"connectionId": "mine"}, "user-1")
    assert error.value.http_code == 400
    repository.add_all.assert_not_called()
    repository.commit.assert_not_called()


@pytest.mark.asyncio
async def test_function_snapshot_rejects_missing_requirement():
    repository = SimpleNamespace(get_requirement=AsyncMock(return_value=None))
    task = SimpleNamespace(requirement_id="", source_content="legacy task source")
    with pytest.raises(AppError, match="请先完成需求分析并导入增强文本"):
        await ai_tasks.build_generate_run_snapshot(repository, "function", task, "run-1")
