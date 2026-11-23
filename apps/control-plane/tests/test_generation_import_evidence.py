"""Import evidence retains input identity without copying credentials or prompts."""

import json
from copy import deepcopy

import pytest

from testing_agent.domain.generation_import_evidence import import_source_evidence


def test_evidence_hashes_actual_inputs_without_copying_sensitive_values():
    snapshot = {
        "source": {
            "taskId": "task",
            "requirementId": "req",
            "sourceFormat": "json",
            "sourceContent": "private requirement text SECRET-CONTENT",
            "instruction": "SECRET-PROMPT",
            "documentDownloadUrl": "https://example.test/?signature=SECRET-URL",
            "bindings": [{"connectionId": "SECRET-CONNECTION", "accessToken": "SECRET-TOKEN"}],
            "sourceRepository": {
                "repositoryId": "repo",
                "branch": "main",
                "commit": "abc",
                "instanceUrl": "https://example.test/?token=SECRET-URL",
            },
            "interfaces": [{"interfaceId": "i1", "headers": {"Authorization": "SECRET-HEADER"}}],
            "functionalCases": [{"caseId": "f1", "title": "SECRET-CASE"}],
        },
        "config": {"password": "SECRET-CONFIG", "caseNames": ["private title"]},
        "currentOutput": "SECRET-OUTPUT",
        "llmConnectionId": "SECRET-LLM",
    }
    evidence = import_source_evidence(snapshot)
    text = json.dumps(evidence, ensure_ascii=False)
    assert (
        "SECRET-" not in text and "private requirement" not in text and "private title" not in text
    )
    assert evidence["source"]["taskId"] == "task"
    assert evidence["interfaceIds"] == ["i1"] and evidence["functionalCaseIds"] == ["f1"]
    changed = deepcopy(snapshot)
    changed["config"]["caseNames"] = ["different"]
    assert import_source_evidence(changed)["configHash"] != evidence["configHash"]


def test_bad_input_identity_fails_closed():
    with pytest.raises(ValueError, match="incomplete"):
        import_source_evidence({"source": {"interfaces": [{}]}, "config": {}})
    with pytest.raises(ValueError, match="incomplete"):
        import_source_evidence({"source": {}, "config": None})
