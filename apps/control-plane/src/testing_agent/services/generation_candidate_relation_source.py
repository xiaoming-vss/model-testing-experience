"""Lock the current functional candidate used by a derived case graph."""

# transaction-bound: the verified source and ancestors stay locked for dispatch.

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_import_source import CurrentImportSource
from testing_agent.domain.generation_source_closure import RootKey
from testing_agent.domain.requirement_artifacts import validate_artifact
from testing_agent.services.ai_task_output import generated_function_cases
from testing_agent.services.generation_current_import_source import lock_current_import_source


@dataclass(frozen=True)
class CandidateRelationSource:
    current: CurrentImportSource
    cases: list[dict[str, Any]]
    material: str

    def identity(self) -> dict[str, str]:
        """Freeze the actual candidate and its entire verified basis."""
        return {
            "candidateId": self.current.candidate_id,
            "snapshotId": self.current.snapshot_id,
            "contentHash": self.current.content_hash,
            "basisHash": self.current.basis_hash,
            "fullLineageHash": self.current.full_lineage_hash,
        }


async def lock_candidate_relation_source(
    session: AsyncSession,
    *,
    requirement_id: str,
    expected_current_token: str,
    current_root_hashes: dict[RootKey, str],
) -> CandidateRelationSource:
    """Resolve only an aligned adopted leaf and its actual frozen material.

    Caller must authorize and lock parent resources and recompute the document
    root before calling. It must hold the resulting locks until the derived
    graph is reserved and committed; this helper does not commit or use a
    client-provided candidate body.
    """
    current = await lock_current_import_source(
        session,
        requirement_id=requirement_id,
        kind="function",
        stage="detailed_cases",
        expected_current_token=expected_current_token,
        current_root_hashes=current_root_hashes,
    )
    cases = generated_function_cases(current.content)
    ids = [str(item.get("case_id") or item.get("caseId") or "").strip() for item in cases]
    if not ids or any(not value for value in ids) or len(ids) != len(set(ids)):
        raise dynamic_error(ErrBadRequest, "用例缺少唯一的 case_id，请重新生成并采用用例")
    source = current.source_snapshot.get("source")
    if not isinstance(source, dict):
        raise dynamic_error(ErrBadRequest, "完整用例缺少材料来源，请重新生成")
    try:
        material = validate_artifact(source.get("sourceContent", ""), "document_extraction")
    except ValueError as exc:
        raise dynamic_error(ErrBadRequest, "完整用例缺少有效的材料来源，请重新生成") from exc
    return CandidateRelationSource(
        current=current,
        cases=cases,
        material=json.dumps(material, ensure_ascii=False, separators=(",", ":")),
    )
