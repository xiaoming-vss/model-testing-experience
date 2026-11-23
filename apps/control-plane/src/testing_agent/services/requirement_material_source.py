"""Prepare verified current material for downstream generation tasks."""

from __future__ import annotations

import json
from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.requirement_artifacts import validate_artifact
from testing_agent.services.generation_current_material import CurrentMaterial


def material_source(material: CurrentMaterial) -> str:
    """Return the complete validated material artifact for downstream prompts."""
    try:
        value = validate_artifact(material.content, "document_extraction")
    except ValueError as exc:
        raise dynamic_error(ErrBadRequest, "当前材料整理内容无效，请重新生成并采用") from exc
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def material_reference_fields(material: CurrentMaterial) -> dict[str, Any]:
    """Freeze the actual current identity without presenting it as a version."""
    return {
        "requirementMaterialCurrent": {
            "candidateId": material.candidate_id,
            "snapshotId": material.snapshot_id,
            "currentToken": material.current_token,
            "taskId": material.task_id,
            "attemptId": material.attempt_id,
            "contentHash": material.content_hash,
            "basisHash": material.basis_hash,
            "lineageHash": material.lineage_hash,
            "documentRootHash": material.document_root_hash,
        }
    }
