"""Build preview bindings from server-verified source and target records."""

from testing_agent.domain.generation_import_preview import ImportPreviewBinding
from testing_agent.domain.generation_import_source import CurrentImportSource
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.repositories.generation_import_targets import ImportTargetState


def import_preview_binding(
    *, actor_id: str, source: CurrentImportSource, target: ImportTargetState
) -> ImportPreviewBinding:
    """Combine scoped, authoritative source and target identities without raw content."""
    if not actor_id or source.requirement_id != target.requirement_id or source.kind != target.kind:
        raise SourceClosureError("source_conflict")
    return ImportPreviewBinding(
        actor_id=actor_id,
        requirement_id=source.requirement_id,
        kind=source.kind,
        stage=source.stage,
        candidate_id=source.candidate_id,
        snapshot_id=source.snapshot_id,
        current_token=source.content_token,
        content_hash=source.content_hash,
        full_lineage_hash=source.full_lineage_hash,
        target_id=target.target_id,
        target_fingerprint=target.fingerprint,
    )
