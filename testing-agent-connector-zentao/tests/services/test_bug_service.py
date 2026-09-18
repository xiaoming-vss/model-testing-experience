import pytest

from app.schemas.zentao.imports import ImportListQuery
from app.services.zentao import ZentaoBugService


class FakeZentaoClient:
    @property
    def config(self):
        return None

    @property
    def is_configured(self) -> bool:
        return True

    async def list_execution_bugs(
        self,
        execution_id: int,
        params: dict[str, str | int],
    ) -> dict[str, object]:
        assert execution_id == 11
        assert params == {"browseType": "all", "recPerPage": 100, "pageID": 1}
        return {
            "status": "success",
            "total": "1",
            "bugs": [
                {
                    "id": 201,
                    "openedDate": "2026-06-01 10:00:00",
                    "resolvedDate": "2026-06-02 11:00:00",
                    "status": "active",
                    "type": "code",
                    "pri": 2,
                    "severity": 3,
                    "title": "Crash on login",
                    "plan": 7,
                    "execution": 11,
                    "module": 5,
                    "product": 1,
                }
            ],
        }


@pytest.mark.anyio
async def test_list_execution_bugs_normalizes_upstream_bug_fields() -> None:
    service = ZentaoBugService(bug_client=FakeZentaoClient())

    result = await service.list_execution_bugs(11, ImportListQuery())

    assert result.total == 1
    assert result.items[0].id == 201
    assert result.items[0].openedDate == "2026-06-01T10:00:00+08:00"
    assert result.items[0].resolvedDate == "2026-06-02T11:00:00+08:00"
    assert result.items[0].status == "active"
    assert result.items[0].type == "code"
    assert result.items[0].pri == 2
    assert result.items[0].severity == 3
    assert result.items[0].title == "Crash on login"
    assert result.items[0].plan == 7
    assert result.items[0].execution == 11
    assert result.items[0].module == 5
    assert result.items[0].product == 1
