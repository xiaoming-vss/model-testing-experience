"""Public UI input provenance, excluding worker URLs and authorization material."""

from copy import deepcopy
from typing import Any


def ui_source_inputs(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Expose only frozen archive metadata and formal functional case content."""
    if not snapshot:
        return None
    archive = snapshot.get("sourceArchive") or {}
    file_id = snapshot.get("sourceArchiveFileId") or ""
    cases = snapshot.get("functionalCases")
    if not file_id and not cases:
        return None
    return {
        "archive": {
            "fileId": file_id,
            **{key: archive[key] for key in ("filename", "sha256", "sizeBytes") if key in archive},
        },
        "cases": deepcopy(cases) if isinstance(cases, list) else [],
    }
