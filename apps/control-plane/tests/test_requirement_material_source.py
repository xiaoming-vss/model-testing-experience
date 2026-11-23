import json
from dataclasses import replace
from pathlib import Path

import pytest

from testing_agent.core.errors import AppError
from testing_agent.services.generation_current_material import CurrentMaterial
from testing_agent.services.requirement_material_source import (
    material_reference_fields,
    material_source,
)


def current_material(content):
    return CurrentMaterial(
        candidate_id="candidate",
        snapshot_id="snapshot",
        candidate_token="candidate-token",
        current_token="current-token",
        task_id="task",
        attempt_id="attempt",
        content=content,
        content_hash="content-hash",
        basis_hash="basis-hash",
        lineage_hash="lineage-hash",
        document_root_hash="document-hash",
    )


def test_material_source_validates_and_preserves_current_artifact_and_identity():
    content = Path(
        "tests/fixtures/requirement_artifacts/readable-material.example.json"
    ).read_text()
    material = current_material(content)
    assert json.loads(material_source(material)) == json.loads(content)
    assert material_reference_fields(material) == {
        "requirementMaterialCurrent": {
            "candidateId": "candidate",
            "snapshotId": "snapshot",
            "currentToken": "current-token",
            "taskId": "task",
            "attemptId": "attempt",
            "contentHash": "content-hash",
            "basisHash": "basis-hash",
            "lineageHash": "lineage-hash",
            "documentRootHash": "document-hash",
        }
    }
    with pytest.raises(AppError, match="当前材料整理内容无效"):
        material_source(replace(material, content='{"artifactType":"requirement_understanding"}'))
