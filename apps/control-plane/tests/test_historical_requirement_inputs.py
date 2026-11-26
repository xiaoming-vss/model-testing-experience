"""Historical relation input tolerates adopted material it cannot read."""

import pytest

from testing_agent.repositories.historical_requirement_materials import HistoricalMaterial
from testing_agent.services import historical_requirement_inputs as inputs


def material(function_id: str, name: str, text: str) -> dict:
    return {
        "id": function_id,
        "name": name,
        "sections": [
            {
                "title": "功能使用与业务规则",
                "items": [{"text": text, "status": "confirmed", "materialBlockIds": [function_id]}],
            }
        ],
    }


@pytest.mark.asyncio
async def test_shortlist_skips_material_that_is_not_readable_material(monkeypatch):
    current = {
        "requirementId": "current",
        "materialSnapshotId": "snapshot-current",
        "items": inputs._items([material("login", "登录", "使用密码登录")]),
    }

    async def no_relations(session, *, project_id, requirement_ids):
        return []

    async def rows(session, *, project_id, current_requirement_id):
        # Legacy document_extraction content has no readable-material sections.
        yield HistoricalMaterial("legacy", "snapshot-legacy", [{"name": "旧功能"}])
        yield HistoricalMaterial(
            "valid", "snapshot-valid", [material("login-history", "登录", "使用密码登录")]
        )

    monkeypatch.setattr(inputs, "read_adopted_relation_results", no_relations)
    monkeypatch.setattr(inputs, "iter_project_materials", rows)

    result = await inputs._shortlist(None, project_id="p", current=current)

    assert [entry["requirementId"] for entry in result] == ["valid"]
