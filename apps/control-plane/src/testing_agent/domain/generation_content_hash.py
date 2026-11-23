"""Stable, conservative content fingerprints for generated artifacts."""

import json
from hashlib import sha256


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def generation_content_hash(content: str, artifact_format: str) -> str:
    """Hash validated artifact content without mixing different formats.

    JSON key order and whitespace do not affect its fingerprint. Text and YAML
    retain all content other than line-ending representation; we do not infer
    YAML semantic equality or strip meaningful whitespace.
    """
    if artifact_format == "json":
        normalized = json.dumps(
            json.loads(content, object_pairs_hook=_unique_object),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    elif artifact_format in {"text", "yaml"}:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    else:
        raise ValueError("unsupported artifact format")
    digest = sha256(f"{artifact_format}\0{normalized}".encode()).hexdigest()
    return f"sha256:{digest}"
