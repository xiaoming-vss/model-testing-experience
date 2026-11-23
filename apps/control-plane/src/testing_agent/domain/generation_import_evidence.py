"""Create a minimal, secret-free audit projection of an actual run snapshot."""

from typing import Any

from testing_agent.domain.request_identity import request_signature

_SOURCE_FIELDS = (
    "taskId",
    "taskType",
    "projectId",
    "sprintId",
    "requirementId",
    "sourceType",
    "sourceFormat",
    "sourceFormatVersion",
    "documentFileId",
    "documentHash",
    "documentType",
    "workflowVersion",
    "apiWorkflowVersion",
    "uiWorkflowVersion",
    "uiSourceBatchId",
)


def import_source_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keep IDs and input fingerprints, never raw prompts, credentials or URLs.

    The complete generated artifact is retained separately. Input content and
    config are hashed rather than copied; this projection cannot reconstruct an
    original prompt or document, but remains useful after attempt deletion.
    """
    source = snapshot.get("source")
    config = snapshot.get("config")
    if not isinstance(source, dict) or not isinstance(config, dict):
        raise ValueError("input snapshot is incomplete")
    fields = {
        key: source[key]
        for key in _SOURCE_FIELDS
        if key in source and isinstance(source[key], (str, int, bool))
    }
    result: dict[str, Any] = {
        "evidenceVersion": "1",
        "source": fields,
        "sourceContentHash": request_signature(
            "import-source-content", {"value": source.get("sourceContent")}
        ),
        "instructionHash": request_signature(
            "import-instruction", {"value": source.get("instruction")}
        ),
        "configHash": request_signature("import-stage-config", config),
        "currentOutputHash": request_signature(
            "import-current-output", {"value": snapshot.get("currentOutput")}
        ),
    }
    for field, id_key, output in (
        ("interfaces", "interfaceId", "interfaceIds"),
        ("functionalCases", "caseId", "functionalCaseIds"),
    ):
        items = source.get(field)
        if isinstance(items, list):
            if any(
                not isinstance(item, dict) or not isinstance(item.get(id_key), str)
                for item in items
            ):
                raise ValueError("input identities are incomplete")
            result[output] = [item[id_key] for item in items]
    repository = source.get("sourceRepository")
    if isinstance(repository, dict):
        identity = {
            key: repository.get(key)
            for key in ("repositoryId", "instanceUrl", "pathWithNamespace", "branch", "commit")
        }
        result["repositoryIdentityHash"] = request_signature("import-ui-repository", identity)
    return result
