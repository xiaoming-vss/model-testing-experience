import pytest

from app.schemas.zentao.imports import ImportListQuery
from app.services.zentao import ZentaoTestTaskService


class FakeZentaoClient:
    @property
    def config(self):
        return None

    @property
    def is_configured(self) -> bool:
        return True

    async def list_testtasks(
        self,
        execution_id: int,
        params: dict[str, str | int],
    ) -> dict[str, object]:
        assert execution_id == 11
        assert params["browseType"] == "all"
        return {
            "status": "success",
            "total": "1",
            "testtasks": [
                {
                    "id": 101,
                    "name": "Regression Test Task",
                    "project": 1,
                    "execution": execution_id,
                    "status": "wait",
                    "begin": "2026-05-01",
                    "end": "2026-05-05",
                    "owner": "tester1",
                    "openedBy": "admin",
                    "type": "system",
                    "pri": 2,
                    "build": 3001,
                    "desc": "Test task desc",
                }
            ],
        }

    async def get_testtask(self, testtask_id: int) -> dict[str, object]:
        assert testtask_id == 101
        return {
            "status": "success",
            "testtask": {
                "id": 101,
                "name": "Regression Test Task",
                "project": 1,
                "execution": 11,
                "desc": "Test task desc",
            },
        }


@pytest.mark.anyio
async def test_list_testtasks_normalizes_upstream_testtask_fields() -> None:
    service = ZentaoTestTaskService(testtask_client=FakeZentaoClient())

    result = await service.list_testtasks(11, ImportListQuery())

    assert result.total == 1
    assert result.items[0].id == 101
    assert result.items[0].project_id == 1
    assert result.items[0].execution_id == 11
    assert result.items[0].name == "Regression Test Task"
    assert result.items[0].status == "wait"
    assert result.items[0].begin == "2026-05-01T00:00:00+08:00"
    assert result.items[0].end == "2026-05-05T00:00:00+08:00"
    assert result.items[0].owner == "tester1"
    assert result.items[0].opened_by == "admin"
    assert result.items[0].type == "system"
    assert result.items[0].description == "Test task desc"


@pytest.mark.anyio
async def test_get_testtask_normalizes_upstream_testtask_fields() -> None:
    service = ZentaoTestTaskService(testtask_client=FakeZentaoClient())

    result = await service.get_testtask(101)

    assert result.id == 101
    assert result.execution_id == 11
    assert result.description == "Test task desc"
