"""Build one worker snapshot from a verified candidate source closure."""

import json
from copy import deepcopy
from typing import Any

from testing_agent.domain.generation_chain import STAGE_CONFIG_FIELDS, artifact_value, stage_names
from testing_agent.domain.generation_root_fingerprints import (
    IncompleteRootInput,
    fingerprint_generation_basis,
    fingerprint_root_input,
)
from testing_agent.domain.generation_source_closure import RootSnapshot, SourceClosureError
from testing_agent.domain.request_identity import request_signature
from testing_agent.domain.requirement_artifacts import validate_artifact
from testing_agent.domain.test_scope_analysis import parse_test_scope
from testing_agent.schemas.generation_candidates import CandidateRunRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_task_output import normalize_config_json
from testing_agent.services.functional_requirement_source import (
    FUNCTIONAL_SOURCE_FORMAT,
    FUNCTIONAL_SOURCE_FORMAT_VERSION,
)
from testing_agent.services.generation_source_selection import ResolvedRunSources


def candidate_request_signature(
    *, requirement_id: str, kind: DesignKind, stage: str, request: CandidateRunRequest
) -> str:
    """Bind an idempotent request to its mode, selections and execution inputs."""
    body = request.model_dump(mode="json", by_alias=True, exclude={"request_id"})
    # Existing requests were signed before this optional concurrency guard was
    # introduced. Preserve their replay signature when no guard was supplied.
    if request.required_current_source is None:
        body.pop("requiredCurrentSource", None)
    return request_signature(
        "generation-candidate-stage-run",
        {"requirementId": requirement_id, "kind": kind, "stage": stage, "request": body},
    )


def build_candidate_input_snapshot(
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    request: CandidateRunRequest,
    sources: ResolvedRunSources,
    source: dict[str, Any],
    attachment_hashes: dict[str, str],
) -> dict[str, Any]:
    """Build the exact immutable snapshot for an already-authorized dispatch.

    ``sources`` must be resolved and locked in the same transaction. ``source``
    must be built from server-controlled task and root inputs, not client data.
    The caller must lock and validate those roots and revision attachments.
    """
    if (
        stage not in stage_names(kind)
        or sources.manifest.generation_mode != request.generation_mode
    ):
        raise SourceClosureError("source_conflict")
    selected = {(item.chain_kind, item.stage): item for item in sources.selected_content}
    if set(selected) != {
        (item.chain_kind, item.stage) for item in sources.manifest.selected_sources
    }:
        raise SourceClosureError("source_conflict")
    frozen_selections = {
        (item.chain_kind, item.stage): item for item in sources.manifest.selected_sources
    }
    if request.generation_mode == "trial":
        supplied = {(item.chain_kind, item.stage): item for item in request.source_selections}
        if set(supplied) != set(frozen_selections):
            raise SourceClosureError("source_conflict")
        for key, choice in supplied.items():
            frozen = frozen_selections[key]
            if choice.source_kind != frozen.source_kind or (
                choice.source_kind == "candidate"
                and (
                    choice.candidate_id != frozen.candidate_id
                    or choice.snapshot_id != frozen.snapshot_id
                )
            ):
                raise SourceClosureError("source_conflict")
    source = deepcopy(source)
    if source.get("requirementId") != requirement_id:
        raise SourceClosureError("source_conflict")
    config = deepcopy(normalize_config_json(request.config_json))
    if set(config) & (
        set(STAGE_CONFIG_FIELDS.values())
        | {"resultYaml", "revisionInstruction", "revisionAttachments"}
    ):
        raise SourceClosureError("source_conflict")
    source["instruction"] = request.instruction or ""
    roots = tuple(
        RootSnapshot(
            item.snapshot_id,
            item.resource_kind,
            item.resource_id,
            item.content_hash,
            item.source_batch_id,
        )
        for item in sources.manifest.root_sources
    )
    root_kind = {
        "requirement_analysis": "requirement_document",
        "api": "api_interfaces",
        "ui": "ui_repository_cases",
    }.get(kind)
    if root_kind is not None:
        try:
            actual = fingerprint_root_input(root_kind, source)  # type: ignore[arg-type]
        except IncompleteRootInput as exc:
            raise SourceClosureError("source_unknown") from exc
        if actual not in roots:
            raise SourceClosureError("source_stale")
    if kind == "function":
        material = next(
            (
                item
                for item in sources.closure_content
                if item.chain_kind == "requirement_analysis" and item.stage == "extracting_text"
            ),
            None,
        )
        if material is None:
            raise SourceClosureError("source_unknown")
        try:
            value = validate_artifact(material.content, "document_extraction")
            source["sourceContent"] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except ValueError as exc:
            raise SourceClosureError("source_unknown") from exc
        source["sourceFormat"] = FUNCTIONAL_SOURCE_FORMAT
        source["sourceFormatVersion"] = FUNCTIONAL_SOURCE_FORMAT_VERSION
    for item in sources.selected_content:
        if item.chain_kind == kind and item.stage in STAGE_CONFIG_FIELDS:
            config[STAGE_CONFIG_FIELDS[item.stage]] = artifact_value(
                item.stage, item.content, item.format
            )
    analysis = selected.get(("function", "requirement_analysis"))
    if kind == "function" and analysis is not None:
        try:
            parse_test_scope(analysis.content)
        except ValueError as exc:
            raise SourceClosureError("source_unknown") from exc
    snapshot: dict[str, Any] = {
        "source": source,
        "config": config,
        "currentOutput": "",
        "llmConnectionId": request.connection_id,
        "requestSignature": candidate_request_signature(
            requirement_id=requirement_id, kind=kind, stage=stage, request=request
        ),
        "candidateInput": sources.manifest.model_dump(mode="json", by_alias=True),
        "candidateProtocol": "single-current/1",
    }
    try:
        snapshot["candidateBasisHash"] = fingerprint_generation_basis(
            kind=kind,
            stage=stage,
            input_snapshot=snapshot,
            roots=roots,
            lineage_hash=sources.manifest.lineage_hash,
            attachment_hashes=attachment_hashes,
        )
    except IncompleteRootInput as exc:
        raise SourceClosureError("source_unknown") from exc
    return snapshot
