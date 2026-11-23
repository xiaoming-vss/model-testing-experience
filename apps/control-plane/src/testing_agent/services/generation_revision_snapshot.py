"""Create a revision input snapshot from a verified frozen candidate."""

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from testing_agent.domain.generation_chain import STAGE_CONFIG_FIELDS, artifact_value
from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_root_fingerprints import (
    IncompleteRootInput,
    fingerprint_generation_basis,
)
from testing_agent.domain.generation_source_closure import RootSnapshot, SourceClosureError
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.schemas.generation_candidates import (
    CandidateRevisionRequest,
    FrozenCandidateInput,
)
from testing_agent.schemas.requirement_design import DesignKind


def build_revision_snapshot(
    *,
    candidate: AiGenerationCandidate,
    kind: DesignKind,
    stage: str,
    request: CandidateRevisionRequest,
    signature: str,
    attempt_id: str,
    actor_id: str,
    attachments: tuple[dict[str, str], ...],
    attachment_hashes: dict[str, str],
    verified_ui_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Preserve the exact upstream branch; the caller verifies and locks it first.

    The caller must authorize the actor, independently verify all roots and the
    complete candidate closure, freeze the parent, verify and attach the images,
    and rebind UI credentials before invoking this function.
    """
    snapshot = deepcopy(candidate.source_snapshot_json)
    if (
        not isinstance(snapshot, dict)
        or not isinstance(snapshot.get("source"), dict)
        or not isinstance(snapshot.get("config"), dict)
        or not isinstance(candidate.source_manifest_json, dict)
        or candidate.disposition != "available"
        or candidate.candidate_token != request.expected_candidate_token
        or candidate.current_attempt_id != request.expected_attempt_id
        or not candidate.content
        or not candidate.format
        or not candidate.lineage_hash
        or not candidate.content_hash
        or not signature
        or not attempt_id
        or not actor_id
        or stage not in STAGE_CONFIG_FIELDS
        or (kind == "ui" and not isinstance(verified_ui_binding, dict))
        or (kind != "ui" and verified_ui_binding is not None)
    ):
        raise SourceClosureError("source_unknown")
    try:
        if generation_content_hash(candidate.content, candidate.format) != candidate.content_hash:
            raise SourceClosureError("source_stale")
        manifest = FrozenCandidateInput.model_validate(candidate.source_manifest_json)
        if manifest.lineage_hash != candidate.lineage_hash:
            raise SourceClosureError("source_conflict")
        manifest = manifest.model_copy(update={"generation_mode": "trial"})
        roots = tuple(
            RootSnapshot(
                item.snapshot_id,
                item.resource_kind,
                item.resource_id,
                item.content_hash,
                item.source_batch_id,
            )
            for item in manifest.root_sources
        )
        ids = [item.get("fileId") for item in attachments]
        if (
            ids != request.attachment_file_ids
            or len(ids) != len(set(ids))
            or set(ids) != set(attachment_hashes)
        ):
            raise SourceClosureError("source_unknown")
        config = snapshot["config"]
        config.pop("revisionInstruction", None)
        config.pop("revisionAttachments", None)
        config[STAGE_CONFIG_FIELDS[stage]] = artifact_value(
            stage, candidate.content, candidate.format
        )
        if attachments:
            config["revisionAttachments"] = [dict(item) for item in attachments]
        snapshot["source"]["instruction"] = request.instruction
        if verified_ui_binding is not None:
            snapshot["source"]["bindings"] = [deepcopy(verified_ui_binding)]
        snapshot.update(
            {
                "currentOutput": candidate.content,
                "revisionInstruction": request.instruction,
                "llmConnectionId": request.connection_id,
                "requestSignature": signature,
                "candidateInput": manifest.model_dump(mode="json", by_alias=True),
                "candidateProtocol": "single-current/2",
                "revisionAttemptId": attempt_id,
                "revisionActorId": actor_id,
                "revisionParent": {
                    "candidateId": candidate.candidate_id,
                    "snapshotId": candidate.snapshot_id,
                    "candidateToken": candidate.candidate_token,
                    "attemptId": candidate.current_attempt_id,
                    "contentHash": candidate.content_hash,
                },
            }
        )
        snapshot["candidateBasisHash"] = fingerprint_generation_basis(
            kind=kind,
            stage=stage,
            input_snapshot=snapshot,
            roots=roots,
            lineage_hash=manifest.lineage_hash,
            attachment_hashes=attachment_hashes,
        )
    except SourceClosureError:
        raise
    except (IncompleteRootInput, ValidationError, ValueError, TypeError) as exc:
        raise SourceClosureError("source_unknown") from exc
    return snapshot
