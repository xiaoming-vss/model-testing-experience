from datetime import UTC, datetime

import pytest

from testing_agent.core.object_storage import ObjectStorageSettings
from testing_agent.domain.zentao_bug_mapping import remote_snapshot
from testing_agent.schemas.bug_zentao_import import ZentaoBugImportPreview
from testing_agent.schemas.bug_zentao_pull import ZentaoRemoteGroupPreview


def test_invalid_import_preview_preserves_empty_nested_objects():
    result = ZentaoBugImportPreview(remote_bug_id=7, state="invalid").model_dump(by_alias=True)
    assert result["snapshot"] == {}
    assert result["converted"] == {}
    assert result["description"] == {}


def test_normalized_import_fields_and_unmapped_values_survive_serialization():
    snapshot = remote_snapshot(
        {"id": 7, "title": "Bug", "status": "active", "assignedTo": "alice", "pri": "9"}
    )
    result = ZentaoBugImportPreview.model_validate(
        {
            "remoteBugId": 7,
            "state": "pending",
            "snapshot": snapshot,
            "converted": {"priority": None, "foundSprintId": ""},
            "description": {"hasImages": True, "hasContent": True},
        }
    ).model_dump(by_alias=True)
    assert result["snapshot"] == snapshot
    assert result["converted"] == {"priority": None, "foundSprintId": ""}
    assert result["description"] == {"hasImages": True, "hasContent": True}


def test_group_preview_keeps_missing_fields_and_extensible_historical_baseline():
    payload = {
        "group": "profile",
        "state": "pending_map",
        "local": {"title": "Bug", "severity": "normal", "priority": "low"},
        "remote": {"title": "Bug", "severity": None, "priority": None},
        "baseline": {
            "local": {"historicalField": {"items": [1, "x", None, True]}},
            "remote": {"providerExtension": "retained"},
            "appliedAt": datetime(2026, 10, 20, tzinfo=UTC),
        },
    }
    preview = ZentaoRemoteGroupPreview.model_validate(payload)
    result = preview.model_dump(by_alias=True, mode="json")
    assert result["local"] == payload["local"]
    assert result["remote"] == payload["remote"]
    assert result["baseline"]["local"] == payload["baseline"]["local"]
    assert result["baseline"]["remote"] == payload["baseline"]["remote"]
    assert result["baseline"]["appliedAt"] == "2026-10-20T00:00:00Z"


@pytest.mark.parametrize("style", ["auto", "path", "virtual"])
def test_storage_addressing_style_accepts_supported_modes(style):
    assert ObjectStorageSettings(addressing_style=style).addressing_style == style


def test_storage_addressing_style_rejects_invalid_mode_before_client_creation():
    with pytest.raises(ValueError, match="addressing_style"):
        ObjectStorageSettings(addressing_style="unsupported")
