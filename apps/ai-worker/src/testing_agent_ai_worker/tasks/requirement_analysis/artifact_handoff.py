"""Read a model's fixed file receipt within this invocation's private output directory."""

import json
from pathlib import Path
from typing import Any

RECEIPT_FILENAMES = {
    "document_extraction": "document-extraction.json",
    "requirement_review": "requirement-review.json",
}


def read_artifact_response(raw: Any, *, kind: str, output_path: Path) -> Any:
    """Resolve only the exact receipt; all business JSON still uses the normal validator."""
    filename = RECEIPT_FILENAMES.get(kind)
    if isinstance(raw, str):
        try:
            pairs = json.loads(raw, object_pairs_hook=lambda items: items)
        except ValueError:
            return raw
        if not isinstance(pairs, list) or not any(
            isinstance(item, tuple) and item[0] == "artifactFile" for item in pairs
        ):
            return raw
        receipt_valid = pairs == [("artifactFile", filename)] if filename else False
    elif isinstance(raw, dict) and "artifactFile" in raw:
        receipt_valid = raw == {"artifactFile": filename} if filename else False
    else:
        return raw
    if not receipt_valid:
        raise ValueError(
            "产物文件回执不合法；本阶段仅支持固定 " + (filename or "产物文件") + " 回执"
        )
    if (
        output_path.is_symlink()
        or output_path.resolve().parent != output_path.parent
        or not output_path.is_file()
    ):
        raise ValueError(f"本次调用的 {filename} 不存在或不是普通产物文件")
    try:
        return output_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("无法读取本次调用的 UTF-8 产物文件") from exc
