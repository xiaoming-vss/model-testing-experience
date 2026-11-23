"""Fingerprint the explicit business inputs of supported generation chains."""

import json
from copy import deepcopy
from hashlib import sha256
from typing import Any, Literal

from testing_agent.domain.generation_chain import stage_names
from testing_agent.domain.generation_source_closure import RootSnapshot

RootKind = Literal["requirement_document", "api_interfaces", "ui_repository_cases"]


class IncompleteRootInput(ValueError):
    """The input cannot be verified from the frozen snapshot."""


def _hash(value: object) -> str:
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:
        raise IncompleteRootInput("business input cannot be fingerprinted") from exc
    return f"sha256:{sha256(encoded).hexdigest()}"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def fingerprint_root_input(kind: RootKind, source: dict[str, Any]) -> RootSnapshot:
    """Hash actual frozen inputs, excluding credentials and ephemeral URLs.

    The caller must load the corresponding current business inputs and run the
    same projection under the required locks before treating a source as valid.
    Run-specific instructions and stage config belong in the separate basis
    fingerprint and are deliberately not treated as mutable business roots.
    """
    batch: str | None = None
    if kind == "requirement_document":
        resource_id = _text(source.get("requirementId"))
        file_id = _text(source.get("documentFileId"))
        document_hash = _text(source.get("documentHash"))
        document_type = _text(source.get("documentType"))
        if not all((resource_id, file_id, document_hash, document_type)):
            raise IncompleteRootInput("requirement document identity or hash is unavailable")
        payload: dict[str, Any] = {
            "fileId": file_id,
            "documentHash": document_hash,
            "documentType": document_type,
            "documentFilename": source.get("documentFilename") or "",
        }
        if document_type == "richtext":
            attachments = source.get("attachmentHashes")
            if not isinstance(attachments, list) or any(
                not isinstance(item, dict)
                or not _text(item.get("fileId"))
                or not _text(item.get("sha256"))
                for item in attachments
            ):
                raise IncompleteRootInput(
                    "rich text attachment identities or hashes are unavailable"
                )
            attachment_ids = [_text(item["fileId"]) for item in attachments]
            if len(attachment_ids) != len(set(attachment_ids)):
                raise IncompleteRootInput("rich text attachments are duplicated")
            payload["attachmentHashes"] = sorted(
                (
                    {"fileId": _text(item["fileId"]), "sha256": _text(item["sha256"])}
                    for item in attachments
                ),
                key=lambda item: item["fileId"],
            )
    elif kind == "api_interfaces":
        resource_id = _text(source.get("taskId"))
        interfaces = source.get("interfaces")
        repositories = source.get("softwareRepositories")
        if (
            not resource_id
            or not _text(source.get("requirementId"))
            or not isinstance(interfaces, list)
            or not interfaces
            or not isinstance(repositories, list)
            or not repositories
            or any(
                not isinstance(item, dict) or not _text(item.get("interfaceId"))
                for item in interfaces
            )
        ):
            raise IncompleteRootInput("selected API interfaces are unavailable")
        ids = [_text(item["interfaceId"]) for item in interfaces]
        if len(ids) != len(set(ids)):
            raise IncompleteRootInput("selected API interfaces are duplicated")
        if any(
            not isinstance(item, dict) or not _text(item.get("softwareRepositoryId"))
            for item in repositories
        ):
            raise IncompleteRootInput("API software repository identity is unavailable")
        repository_ids = [_text(item["softwareRepositoryId"]) for item in repositories]
        if len(repository_ids) != len(set(repository_ids)) or any(
            _text(item.get("softwareRepositoryId")) not in repository_ids for item in interfaces
        ):
            raise IncompleteRootInput("API interfaces do not match their repositories")
        payload = {
            "interfaces": interfaces,
            "softwareRepositories": repositories,
            "requirementId": source.get("requirementId") or "",
        }
    elif kind == "ui_repository_cases":
        resource_id = _text(source.get("taskId"))
        repository = source.get("sourceRepository")
        cases = source.get("functionalCases")
        batch = _text(source.get("uiSourceBatchId")) or None
        if (
            not resource_id
            or not _text(source.get("requirementId"))
            or not isinstance(repository, dict)
            or not isinstance(cases, list)
            or not cases
            or not batch
            or any(
                not _text(repository.get(key))
                for key in ("repositoryId", "instanceUrl", "pathWithNamespace", "branch", "commit")
            )
            or any(not isinstance(item, dict) or not _text(item.get("caseId")) for item in cases)
        ):
            raise IncompleteRootInput("UI repository pin, cases or batch are unavailable")
        ids = [_text(item["caseId"]) for item in cases]
        if len(ids) != len(set(ids)):
            raise IncompleteRootInput("selected UI cases are duplicated")
        payload = {
            "repository": {
                key: repository.get(key) or ""
                for key in ("repositoryId", "instanceUrl", "pathWithNamespace", "branch", "commit")
            },
            "functionalCases": cases,
        }
    else:
        raise IncompleteRootInput("unsupported root input")
    content_hash = _hash(payload)
    snapshot_id = _hash(
        {"kind": kind, "resourceId": resource_id, "contentHash": content_hash, "batch": batch}
    )[7:]
    return RootSnapshot(snapshot_id, kind, resource_id, content_hash, batch)


def fingerprint_generation_basis(
    *,
    kind: str,
    stage: str,
    input_snapshot: dict[str, Any],
    roots: tuple[RootSnapshot, ...],
    lineage_hash: str,
    attachment_hashes: dict[str, str],
) -> str:
    """Hash a frozen run's semantic inputs, excluding transient selection data.

    The caller must supply a server-verified lineage and hashes for any revision
    attachments. The snapshot must be the one actually sent to the worker.
    """
    try:
        valid_stage = stage in stage_names(kind)
    except KeyError:
        valid_stage = False
    source = input_snapshot.get("source")
    config = input_snapshot.get("config")
    if (
        not valid_stage
        or not isinstance(source, dict)
        or not isinstance(config, dict)
        or not roots
        or not lineage_hash
    ):
        raise IncompleteRootInput("generation basis is incomplete")
    source = deepcopy(source)
    config = deepcopy(config)
    for key in (
        "runId",
        "attemptId",
        "documentDownloadUrl",
        "gitlabCredentialsUrl",
        "bindings",
        "uiSourceBatchId",
        "generationMode",
        "sourceSelections",
        "selectedSources",
        "requestId",
        "requestSignature",
        "candidateToken",
        "contentToken",
        "expectedCandidateToken",
        "expectedCurrentToken",
        "expectedAttemptId",
    ):
        source.pop(key, None)
        config.pop(key, None)
    repository = source.get("sourceRepository")
    if isinstance(repository, dict):
        source["sourceRepository"] = {
            key: repository.get(key) or ""
            for key in ("repositoryId", "instanceUrl", "pathWithNamespace", "branch", "commit")
        }
    if kind == "requirement_analysis":
        content = source.get("sourceContent")
        document_url = input_snapshot["source"].get("documentDownloadUrl")
        is_temporary_url = isinstance(content, str) and (
            (bool(document_url) and content == document_url)
            or (
                content.startswith("/internal/ai-worker/tasks/")
                and content.endswith("/requirement-document")
            )
            or (content.startswith("/v1/requirements/") and content.endswith("/download"))
        )
        if is_temporary_url:
            if not source.get("documentFileId") or not source.get("documentHash"):
                raise IncompleteRootInput("document referenced by temporary URL is unknown")
            source["sourceContent"] = {
                "documentFileId": source["documentFileId"],
                "documentHash": source["documentHash"],
            }
    current_output = input_snapshot.get("currentOutput") or ""
    revision = _text(input_snapshot.get("revisionInstruction")) or _text(
        config.get("revisionInstruction")
    )
    if not revision and current_output:
        raise IncompleteRootInput("effective revision instruction is unavailable")
    if revision:
        config["revisionInstruction"] = revision
    else:
        config.pop("revisionInstruction", None)
    attachments = config.pop("revisionAttachments", [])
    if attachments and not revision:
        raise IncompleteRootInput("revision attachments require a revision instruction")
    if revision and attachments:
        if not isinstance(attachments, list):
            raise IncompleteRootInput("revision attachments are invalid")
        projected = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                raise IncompleteRootInput("revision attachment is invalid")
            file_id = _text(attachment.get("fileId"))
            digest = attachment_hashes.get(file_id)
            if not file_id or not digest:
                raise IncompleteRootInput("revision attachment content hash is unavailable")
            projected.append(
                {
                    "fileId": file_id,
                    "sha256": digest,
                    "filename": attachment.get("filename") or "",
                    "contentType": attachment.get("contentType") or "",
                }
            )
        config["revisionAttachments"] = projected
    root_values = [
        {
            "snapshotId": root.snapshot_id,
            "resourceKind": root.resource_kind,
            "resourceId": root.resource_id,
            "contentHash": root.content_hash,
            "sourceBatchId": root.source_batch_id,
        }
        for root in sorted(
            roots, key=lambda item: (item.resource_kind, item.resource_id, item.snapshot_id)
        )
    ]
    payload = {
        "chainKind": kind,
        "stage": stage,
        "source": source,
        "config": config,
        "currentOutput": current_output,
        "roots": root_values,
        "lineageHash": lineage_hash,
    }
    if input_snapshot.get("candidateProtocol") == "single-current/2":
        parent = input_snapshot.get("revisionParent")
        keys = ("candidateId", "snapshotId", "candidateToken", "attemptId", "contentHash")
        revision_attempt = _text(input_snapshot.get("revisionAttemptId"))
        revision_actor = _text(input_snapshot.get("revisionActorId"))
        if (
            not isinstance(parent, dict)
            or any(not _text(parent.get(key)) for key in keys)
            or not revision_attempt
            or not revision_actor
        ):
            raise IncompleteRootInput("revision parent identity is unavailable")
        payload["revisionParent"] = {key: parent[key] for key in keys}
        payload["revisionAttemptId"] = revision_attempt
        payload["revisionActorId"] = revision_actor
    return _hash(payload)
