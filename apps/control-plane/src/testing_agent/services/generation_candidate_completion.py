"""Append a candidate for a successful candidate-protocol worker attempt."""

# transaction-bound: the worker, stage, attempt and candidate share one commit.

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.generation_root_fingerprints import (
    IncompleteRootInput,
    fingerprint_generation_basis,
)
from testing_agent.domain.generation_source_closure import RootSnapshot
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    RequirementGenerationChain,
)
from testing_agent.models.stored_file import StoredFile
from testing_agent.repositories.generation_candidate_creation import (
    CandidateProvenance,
    create_candidate_from_successful_attempt,
)
from testing_agent.repositories.generation_root_inputs import lock_revision_attachment_hashes
from testing_agent.schemas.generation_candidates import FrozenCandidateInput


async def publish_candidate_attempt(
    session: AsyncSession, *, stage: AiGenerationStage, attempt: AiGenerationAttempt
) -> None:
    """Append exactly once; caller owns authorization, worker lock and transaction.

    This only accepts server-built ``candidateProtocol`` snapshots. The frozen
    basis is recomputed from the persisted attempt; source validity against
    current business roots is evaluated separately before reuse or adoption.
    Revision attempts must identify their exact frozen same-stage parent and
    attached images; source eligibility is checked again when the result is used.
    """
    snapshot = attempt.input_snapshot_json or {}
    protocol = snapshot.get("candidateProtocol")
    if protocol is None:
        return
    if protocol not in {"single-current/1", "single-current/2"} or not isinstance(
        snapshot.get("candidateInput"), dict
    ):
        raise ErrBadRequest()
    config = snapshot.get("config")
    if not isinstance(config, dict):
        raise ErrBadRequest()
    if protocol == "single-current/1" and (
        snapshot.get("currentOutput")
        or snapshot.get("revisionInstruction")
        or config.get("revisionInstruction")
        or config.get("revisionAttachments")
    ):
        raise ErrBadRequest()
    chain = await session.scalar(
        select(RequirementGenerationChain).where(
            RequirementGenerationChain.task_id == stage.task_id
        )
    )
    if chain is None:
        raise ErrBadRequest()
    attachment_hashes: dict[str, str] = {}
    parent_id = None
    parent: AiGenerationCandidate | None = None
    if protocol == "single-current/2":
        parent_ref = snapshot.get("revisionParent")
        revision = snapshot.get("revisionInstruction")
        if (
            attempt.operation != "revise"
            or snapshot.get("revisionAttemptId") != attempt.id
            or snapshot.get("revisionActorId") != attempt.requested_by
            or not isinstance(parent_ref, dict)
            or not isinstance(parent_ref.get("candidateId"), str)
            or not isinstance(revision, str)
            or not revision.strip()
            or attempt.revision_instruction != revision
            or config.get("revisionInstruction")
        ):
            raise ErrBadRequest()
        parent_id = parent_ref["candidateId"]
        parent = await session.scalar(
            select(AiGenerationCandidate)
            .where(
                AiGenerationCandidate.candidate_id == parent_id,
                AiGenerationCandidate.chain_id == chain.chain_id,
                AiGenerationCandidate.stage_id == stage.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            parent is None
            or parent_ref.get("snapshotId") != parent.snapshot_id
            or parent_ref.get("attemptId") != parent.current_attempt_id
            or parent_ref.get("contentHash") != parent.content_hash
            or snapshot.get("currentOutput") != parent.content
            or not isinstance(parent_ref.get("candidateToken"), str)
            or not parent_ref["candidateToken"]
            or (
                parent.disposition == "available"
                and parent_ref["candidateToken"] != parent.candidate_token
            )
        ):
            raise ErrBadRequest()
        attachments = config.get("revisionAttachments") or []
        if not isinstance(attachments, list):
            raise ErrBadRequest()
        ids: list[str] = []
        for item in attachments:
            file_id = item.get("fileId") if isinstance(item, dict) else None
            if not isinstance(file_id, str) or not file_id or file_id in ids:
                raise ErrBadRequest()
            ids.append(file_id)
        project_id = await session.scalar(
            select(AiGenerateTask.project_id).where(AiGenerateTask.task_id == chain.task_id)
        )
        if not project_id:
            raise ErrBadRequest()
        try:
            attachment_hashes = await lock_revision_attachment_hashes(
                session, project_id=project_id, file_ids=tuple(ids)
            )
        except IncompleteRootInput as exc:
            raise ErrBadRequest() from exc
        files = list(
            (
                await session.scalars(
                    select(StoredFile).where(StoredFile.file_id.in_(ids)).with_for_update()
                )
            ).all()
        )
        by_id = {item.file_id: item for item in files}
        if set(by_id) != set(ids) or any(
            by_id[item["fileId"]].resource_id != attempt.id
            or by_id[item["fileId"]].uploaded_by != attempt.requested_by
            or by_id[item["fileId"]].filename != item.get("filename")
            or by_id[item["fileId"]].content_type != item.get("contentType")
            for item in attachments
        ):
            raise ErrBadRequest()
    try:
        manifest = FrozenCandidateInput.model_validate(snapshot["candidateInput"])
        if protocol == "single-current/2":
            if parent is None or manifest.generation_mode != "trial":
                raise ErrBadRequest()
            parent_manifest = FrozenCandidateInput.model_validate(parent.source_manifest_json)
            if manifest.model_dump(exclude={"generation_mode"}) != parent_manifest.model_dump(
                exclude={"generation_mode"}
            ):
                raise ErrBadRequest()
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
        basis = fingerprint_generation_basis(
            kind=chain.kind,
            stage=stage.stage,
            input_snapshot=snapshot,
            roots=roots,
            lineage_hash=manifest.lineage_hash,
            attachment_hashes=attachment_hashes,
        )
    except (ValidationError, IncompleteRootInput, TypeError, ValueError) as exc:
        raise ErrBadRequest() from exc
    if basis != snapshot.get("candidateBasisHash"):
        raise ErrBadRequest()
    await create_candidate_from_successful_attempt(
        session,
        chain_id=chain.chain_id,
        stage_id=stage.id,
        attempt_id=attempt.id,
        provenance=CandidateProvenance(
            generation_mode=manifest.generation_mode,
            source_manifest=manifest.model_dump(mode="json", by_alias=True),
            lineage_hash=manifest.lineage_hash,
            basis_hash=basis,
            derived_from_candidate_id=parent_id,
        ),
    )
