"""Preview and import the verified current leaf with self-contained receipts."""

# transaction-bound: receipt reservation, target changes and audit records share one commit.

from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.db.savepoint import ensure_outer_transaction
from testing_agent.domain.generation_import_source import CurrentImportSource
from testing_agent.domain.generation_source_closure import RootKey
from testing_agent.domain.request_identity import request_signature
from testing_agent.repositories.generation_import_receipts import (
    read_completed_import_request,
    record_current_import,
    reserve_import_request,
)
from testing_agent.schemas.generation_candidates import CurrentImportRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_task_access import GenerationImportContext
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.function_generate_import import import_function_run
from testing_agent.services.generation_import_guard import (
    prepare_import_preview,
    verify_import_preview,
)
from testing_agent.services.ui_generate_import import import_ui_run


@dataclass(frozen=True)
class CurrentImportPreview:
    current_token: str
    full_lineage_hash: str
    content_hash: str
    basis_hash: str
    candidate_id: str
    target_id: str
    preview_token: str
    preview_expires_at: int
    requires_confirmation: bool
    conflicts: list[dict[str, Any]]


class _ConfirmationRequired(Exception):
    def __init__(self, conflicts: list[dict[str, Any]]) -> None:
        self.conflicts = conflicts


def current_import_signature(
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    request: CurrentImportRequest,
    actor_id: str,
) -> str:
    return request_signature(
        "generation-current-import",
        {
            "requirementId": requirement_id,
            "kind": kind,
            "stage": stage,
            "actorId": actor_id,
            "request": request.model_dump(mode="json", by_alias=True, exclude={"request_id"}),
        },
    )


class CurrentImportCoordinator:
    """Internal transaction operations; HTTP authorization is a caller concern."""

    def __init__(
        self, context: GenerationImportContext, api_importer: ApiCandidateImporter
    ) -> None:
        if context.repository.session is not api_importer.repository.session:
            raise ValueError("import dependencies must share one transaction")
        self.context = context
        self.api_importer = api_importer
        self.session: AsyncSession = context.repository.session

    async def replay(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        request: CurrentImportRequest,
        actor_id: str,
    ) -> dict[str, Any] | None:
        """Read an already completed request after authorization, without source access."""
        if not actor_id:
            raise ErrBadRequest()
        result = await read_completed_import_request(
            self.session,
            request_id=str(request.request_id),
            requirement_id=requirement_id,
            actor_id=actor_id,
            fingerprint=current_import_signature(
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                actor_id=actor_id,
            ),
        )
        return {**result, "replayed": True} if result is not None else None

    async def _apply(
        self,
        source: CurrentImportSource,
        *,
        target_id: str,
        actor_id: str,
        confirm_overwrite: bool,
        preview_only: bool,
    ) -> dict[str, Any]:
        source_run = SimpleNamespace(
            run_id=source.source_attempt_id or source.candidate_id,
            requirement_id=source.requirement_id,
            snapshot_json=deepcopy(source.source_snapshot.get("source") or {}),
            result_yaml=source.content,
            import_status="",
            imported_targets=[],
            imported_at=None,
        )
        if source.kind == "function":
            return await import_function_run(
                self.context,
                source_run.run_id,
                confirm_overwrite,
                actor_id,
                artifact_content=source.content,
                allow_reimport=True,
                approved_source=source_run,
                preview_only=preview_only,
                locking_reads=True,
            )
        if source.kind == "api":
            return await self.api_importer.import_api_run(
                source_run.run_id,
                target_id,
                confirm_overwrite,
                actor_id,
                artifact_content=source.content,
                allow_reimport=True,
                approved_source=source_run,
                preview_only=preview_only,
                locking_reads=True,
            )
        if source.kind == "ui":
            return await import_ui_run(
                self.context,
                source_run.run_id,
                target_id,
                confirm_overwrite,
                actor_id,
                artifact_content=source.content,
                allow_reimport=True,
                approved_source=source_run,
                preview_only=preview_only,
            )
        raise ErrBadRequest()

    async def preview(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        current_token: str,
        target_id: str,
        actor_id: str,
        current_root_hashes: dict[RootKey, str],
        secret: str,
        now: int | None = None,
    ) -> CurrentImportPreview:
        """Read conflicts under locks; caller authorizes, owns locks and ends transaction."""
        preview = await prepare_import_preview(
            self.session,
            requirement_id=requirement_id,
            kind=kind,
            stage=stage,
            current_token=current_token,
            target_id=target_id,
            actor_id=actor_id,
            current_root_hashes=current_root_hashes,
            secret=secret,
            now=now,
        )
        result = await self._apply(
            preview.source,
            target_id=target_id,
            actor_id=actor_id,
            confirm_overwrite=False,
            preview_only=True,
        )
        conflicts = result.get("conflicts") or []
        if not isinstance(conflicts, list) or any(not isinstance(item, dict) for item in conflicts):
            raise ErrBadRequest()
        return CurrentImportPreview(
            current_token=preview.source.content_token,
            full_lineage_hash=preview.source.full_lineage_hash,
            content_hash=preview.source.content_hash,
            basis_hash=preview.source.basis_hash,
            candidate_id=preview.source.candidate_id,
            target_id=target_id,
            preview_token=preview.preview_token,
            preview_expires_at=preview.expires_at,
            requires_confirmation=bool(conflicts),
            conflicts=conflicts,
        )

    async def execute(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        request: CurrentImportRequest,
        actor_id: str,
        current_root_hashes: dict[RootKey, str],
        secret: str,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Recheck preview, change assets and write receipts without implicit commit.

        The caller reauthorizes the actor and holds parent/root locks. On success
        it commits; on any exception it rolls back. A replay returns its recorded
        result before touching sources or targets and never repeats the import.
        """
        if not actor_id:
            raise ErrBadRequest()
        fingerprint = current_import_signature(
            requirement_id=requirement_id,
            kind=kind,
            stage=stage,
            request=request,
            actor_id=actor_id,
        )
        await self.session.run_sync(ensure_outer_transaction)
        try:
            async with self.session.begin_nested():
                reservation, replayed = await reserve_import_request(
                    self.session,
                    request_id=str(request.request_id),
                    fingerprint=fingerprint,
                    requirement_id=requirement_id,
                    actor_id=actor_id,
                )
                if replayed:
                    assert reservation.result_json is not None
                    return {**deepcopy(reservation.result_json), "replayed": True}
                source, _ = await verify_import_preview(
                    self.session,
                    requirement_id=requirement_id,
                    kind=kind,
                    stage=stage,
                    request=request,
                    actor_id=actor_id,
                    current_root_hashes=current_root_hashes,
                    secret=secret,
                    now=now,
                )
                result = await self._apply(
                    source,
                    target_id=request.target_id,
                    actor_id=actor_id,
                    confirm_overwrite=request.confirm_overwrite,
                    preview_only=False,
                )
                if result.get("requiresConfirmation"):
                    conflicts = result.get("conflicts") or []
                    if not isinstance(conflicts, list) or any(
                        not isinstance(item, dict) for item in conflicts
                    ):
                        raise ErrBadRequest()
                    raise _ConfirmationRequired(conflicts)
                changes = result.get("importChanges")
                if not isinstance(changes, list) or any(
                    not isinstance(item, dict) for item in changes
                ):
                    raise ErrBadRequest()
                recorded = await record_current_import(
                    self.session,
                    request=reservation,
                    source=source,
                    target_id=request.target_id,
                    actor_id=actor_id,
                    changes=changes,
                )
                return {**recorded, "replayed": False}
        except _ConfirmationRequired as exc:
            return {
                "imported": False,
                "requiresConfirmation": True,
                "conflicts": exc.conflicts,
                "replayed": False,
            }
