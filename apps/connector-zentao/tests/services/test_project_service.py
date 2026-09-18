import pytest

from app.schemas.zentao.imports import ImportListQuery
from app.services.zentao import ZentaoProjectService


class FakeProjectClient:
    async def list_projects(self, params: dict[str, str | int]) -> dict[str, object]:
        assert params["browseType"] == "all"
        assert params["recPerPage"] == 100
        assert params["pageID"] == 1
        return {
            "status": "success",
            "pager": {"recTotal": "1"},
            "projects": [
                {
                    "id": 2,
                    "name": "Demo Project",
                    "code": 1001,
                    "desc": "Project desc",
                    "status": "doing",
                    "model": "scrum",
                    "begin": "2026-01-01",
                    "deleted": "0",
                }
            ],
        }

    async def get_project(self, project_id: int) -> dict[str, object]:
        assert project_id == 2
        return {
            "status": "success",
            "project": {
                "id": "2",
                "name": "Demo Project",
                "code": "1001",
                "description": "Project desc",
                "status": "doing",
                "begin": "2026-01-01",
                "deleted": "false",
            },
        }


@pytest.mark.anyio
async def test_list_projects_normalizes_upstream_project_fields() -> None:
    service = ZentaoProjectService(project_client=FakeProjectClient())

    result = await service.list_projects(ImportListQuery())

    assert result.total == 1
    assert result.items[0].id == 2
    assert result.items[0].code == "1001"
    assert result.items[0].name == "Demo Project"
    assert result.items[0].description == "Project desc"
    assert result.items[0].begin == "2026-01-01T00:00:00+08:00"
    assert result.items[0].deleted is False


@pytest.mark.anyio
async def test_get_project_normalizes_upstream_project_fields() -> None:
    service = ZentaoProjectService(project_client=FakeProjectClient())

    result = await service.get_project(2)

    assert result.id == 2
    assert result.name == "Demo Project"
    assert result.description == "Project desc"
