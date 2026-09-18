import pytest

from app.schemas.zentao.imports import ImportListQuery
from app.services.zentao import ZentaoExecutionService


class FakeZentaoClient:
    @property
    def config(self):
        return None

    @property
    def is_configured(self) -> bool:
        return True

    async def list_executions(
        self,
        project_id: int,
        params: dict[str, str | int],
    ) -> dict[str, object]:
        assert project_id == 2
        assert params["browseType"] == "all"
        return {
            "status": "success",
            "count": "1",
            "executions": [
                {
                    "id": 11,
                    "name": "Sprint 1",
                    "desc": "Execution desc",
                    "status": "wait",
                    "project": project_id,
                    "begin": "2026-01-02",
                }
            ],
        }

    async def get_execution(self, execution_id: int) -> dict[str, object]:
        assert execution_id == 11
        return {
            "status": "success",
            "execution": {
                "id": 11,
                "name": "Sprint 1",
                "project": 2,
                "parent": "",
                "desc": "Execution desc",
            },
        }

    async def list_execution_stories(self, execution_id: int) -> dict[str, object]:
        assert execution_id == 11
        return {
            "status": "success",
            "total": "1",
            "stories": [
                {
                    "id": "21",
                    "title": "Support login by phone",
                    "product": "1",
                    "module": "2",
                    "plan": "3",
                    "status": "active",
                    "stage": "developing",
                    "pri": "2",
                    "assignedTo": "dev1",
                    "openedBy": "pm1",
                    "openedDate": "2026-05-01 10:00:00",
                }
            ],
        }


@pytest.mark.anyio
async def test_list_executions_normalizes_upstream_execution_fields() -> None:
    service = ZentaoExecutionService(execution_client=FakeZentaoClient())

    result = await service.list_executions(2, ImportListQuery())

    assert result.total == 1
    assert result.items[0].id == 11
    assert result.items[0].project_id == 2
    assert result.items[0].name == "Sprint 1"
    assert result.items[0].description == "Execution desc"
    assert result.items[0].begin == "2026-01-02T00:00:00+08:00"


@pytest.mark.anyio
async def test_get_execution_normalizes_upstream_execution_fields() -> None:
    service = ZentaoExecutionService(execution_client=FakeZentaoClient())

    result = await service.get_execution(11)

    assert result.id == 11
    assert result.project_id == 2
    assert result.parent_id is None


@pytest.mark.anyio
async def test_list_execution_stories_normalizes_upstream_story_fields() -> None:
    service = ZentaoExecutionService(execution_client=FakeZentaoClient())

    result = await service.list_execution_stories(11)

    assert result.total == 1
    assert result.items[0].id == 21
    assert result.items[0].title == "Support login by phone"
    assert result.items[0].product_id == 1
    assert result.items[0].module_id == 2
    assert result.items[0].plan_id == 3
    assert result.items[0].priority == "P2"
    assert result.items[0].assigned_to == "dev1"
    assert result.items[0].opened_by == "pm1"
    assert result.items[0].created_at == "2026-05-01T10:00:00+08:00"
