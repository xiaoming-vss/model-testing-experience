"""Frozen root hashes track consumed inputs without transient credentials or URLs."""

from copy import deepcopy

import pytest

from testing_agent.domain.generation_root_fingerprints import (
    IncompleteRootInput,
    fingerprint_generation_basis,
    fingerprint_root_input,
)


def test_requirement_document_uses_file_identity_and_content_hash_not_download_url():
    source = {
        "requirementId": "req",
        "documentFileId": "file",
        "documentHash": "doc-hash",
        "documentType": "docx",
        "documentFilename": "需求.docx",
        "documentDownloadUrl": "/temporary/one",
    }
    original = fingerprint_root_input("requirement_document", source)
    assert original == fingerprint_root_input(
        "requirement_document", {**source, "documentDownloadUrl": "/temporary/two"}
    )
    assert (
        original.content_hash
        != fingerprint_root_input(
            "requirement_document", {**source, "documentHash": "changed"}
        ).content_hash
    )
    with pytest.raises(IncompleteRootInput):
        fingerprint_root_input("requirement_document", {**source, "documentHash": ""})


def test_richtext_cannot_ignore_embedded_attachment_changes():
    source = {
        "requirementId": "req",
        "documentFileId": "file",
        "documentHash": "doc-hash",
        "documentType": "richtext",
        "attachmentHashes": [{"fileId": "image", "sha256": "image-hash"}],
    }
    original = fingerprint_root_input("requirement_document", source)
    changed = {**source, "attachmentHashes": [{"fileId": "image", "sha256": "changed"}]}
    assert (
        original.content_hash
        != fingerprint_root_input("requirement_document", changed).content_hash
    )
    with pytest.raises(IncompleteRootInput):
        fingerprint_root_input(
            "requirement_document",
            {key: value for key, value in source.items() if key != "attachmentHashes"},
        )


def test_api_input_tracks_selected_interfaces_order_definitions_and_repository():
    source = {
        "taskId": "task",
        "requirementId": "req",
        "name": "API 测试",
        "instruction": "补充边界",
        "interfaces": [
            {"interfaceId": "one", "softwareRepositoryId": "repo", "method": "GET", "path": "/one"},
            {
                "interfaceId": "two",
                "softwareRepositoryId": "repo",
                "method": "POST",
                "path": "/two",
            },
        ],
        "softwareRepositories": [{"softwareRepositoryId": "repo", "basePath": "/v1"}],
        "llmConnectionId": "private-a",
    }
    original = fingerprint_root_input("api_interfaces", source)
    assert original == fingerprint_root_input(
        "api_interfaces", {**source, "llmConnectionId": "private-b"}
    )
    assert original == fingerprint_root_input(
        "api_interfaces", {**source, "instruction": "another run's instruction"}
    )
    changed = deepcopy(source)
    changed["interfaces"][0]["path"] = "/changed"
    assert original.content_hash != fingerprint_root_input("api_interfaces", changed).content_hash
    assert (
        original.content_hash
        != fingerprint_root_input(
            "api_interfaces", {**source, "interfaces": list(reversed(source["interfaces"]))}
        ).content_hash
    )
    with pytest.raises(IncompleteRootInput):
        fingerprint_root_input(
            "api_interfaces", {**source, "interfaces": [source["interfaces"][0]] * 2}
        )


def test_ui_input_tracks_pin_selected_cases_and_batch_not_access_metadata():
    source = {
        "taskId": "task",
        "requirementId": "req",
        "uiSourceBatchId": "batch-a",
        "sourceRepository": {
            "repositoryId": "repo",
            "instanceUrl": "https://git.example",
            "pathWithNamespace": "group/repo",
            "branch": "main",
            "commit": "abc",
            "resolvedAt": "today",
            "commitMode": "latest",
            "bindingId": "binding-a",
        },
        "functionalCases": [{"caseId": "case-1", "title": "登录", "steps": ["输入账号"]}],
        "bindings": [{"connectionId": "private-a", "cloneUrl": "private-url"}],
    }
    original = fingerprint_root_input("ui_repository_cases", source)
    metadata = deepcopy(source)
    metadata["sourceRepository"].update(
        {"resolvedAt": "tomorrow", "commitMode": "profile", "bindingId": "binding-b"}
    )
    metadata["bindings"] = [{"connectionId": "private-b"}]
    assert original == fingerprint_root_input("ui_repository_cases", metadata)
    commit = deepcopy(source)
    commit["sourceRepository"]["commit"] = "different"
    assert (
        original.content_hash != fingerprint_root_input("ui_repository_cases", commit).content_hash
    )
    case = deepcopy(source)
    case["functionalCases"][0]["steps"] = ["输入密码"]
    assert original.content_hash != fingerprint_root_input("ui_repository_cases", case).content_hash
    another_batch = fingerprint_root_input(
        "ui_repository_cases", {**source, "uiSourceBatchId": "batch-b"}
    )
    assert original.content_hash == another_batch.content_hash
    assert original.snapshot_id != another_batch.snapshot_id
    with pytest.raises(IncompleteRootInput):
        fingerprint_root_input("ui_repository_cases", {**source, "uiSourceBatchId": ""})


def test_basis_tracks_instruction_and_attachments_but_not_temporary_metadata():
    source = {
        "requirementId": "req",
        "documentFileId": "file",
        "documentHash": "doc-hash",
        "documentType": "docx",
        "documentFilename": "requirement.docx",
        "documentDownloadUrl": "/internal/ai-worker/tasks/one/requirement-document",
        "sourceContent": "/internal/ai-worker/tasks/one/requirement-document",
        "instruction": "revise",
        "generationMode": "trial",
        "requestId": "old-request",
    }
    root = fingerprint_root_input("requirement_document", source)
    snapshot = {
        "source": source,
        "config": {
            "reviewOutput": {"result": "old"},
            "revisionAttachments": [{"fileId": "image", "filename": "image.png"}],
        },
        "currentOutput": "old result",
        "revisionInstruction": "revise",
    }
    args = {
        "kind": "requirement_analysis",
        "stage": "requirement_review",
        "roots": (root,),
        "lineage_hash": "lineage",
        "attachment_hashes": {"image": "image-hash"},
    }
    original = fingerprint_generation_basis(input_snapshot=snapshot, **args)
    same = deepcopy(snapshot)
    same["source"].update(
        {
            "documentDownloadUrl": "/internal/ai-worker/tasks/two/requirement-document",
            "sourceContent": "/internal/ai-worker/tasks/two/requirement-document",
            "generationMode": "current",
            "requestId": "new-request",
        }
    )
    assert fingerprint_generation_basis(input_snapshot=same, **args) == original
    changed = deepcopy(snapshot)
    changed["source"]["instruction"] = "different"
    assert fingerprint_generation_basis(input_snapshot=changed, **args) != original
    assert (
        fingerprint_generation_basis(
            input_snapshot=snapshot, **{**args, "attachment_hashes": {"image": "different"}}
        )
        != original
    )
    with pytest.raises(IncompleteRootInput, match="attachment"):
        fingerprint_generation_basis(input_snapshot=snapshot, **{**args, "attachment_hashes": {}})
    missing_revision = {
        key: value for key, value in snapshot.items() if key != "revisionInstruction"
    }
    with pytest.raises(IncompleteRootInput, match="revision instruction"):
        fingerprint_generation_basis(input_snapshot=missing_revision, **args)
    unbound_attachment = deepcopy(missing_revision)
    unbound_attachment["currentOutput"] = ""
    with pytest.raises(IncompleteRootInput, match="attachments require"):
        fingerprint_generation_basis(input_snapshot=unbound_attachment, **args)


def test_basis_tracks_actual_stage_config_without_selection_tokens():
    root = fingerprint_root_input(
        "api_interfaces",
        {
            "taskId": "task",
            "requirementId": "req",
            "interfaces": [{"interfaceId": "i", "softwareRepositoryId": "r"}],
            "softwareRepositories": [{"softwareRepositoryId": "r"}],
        },
    )
    snapshot = {
        "source": {"instruction": "check"},
        "config": {"apiExtraction": {"id": 1}, "expectedCurrentToken": "old"},
    }
    args = {
        "kind": "api",
        "stage": "api_design",
        "roots": (root,),
        "lineage_hash": "lineage",
        "attachment_hashes": {},
    }
    first = fingerprint_generation_basis(input_snapshot=snapshot, **args)
    token_changed = deepcopy(snapshot)
    token_changed["config"]["expectedCurrentToken"] = "new"
    assert fingerprint_generation_basis(input_snapshot=token_changed, **args) == first
    input_changed = deepcopy(snapshot)
    input_changed["config"]["apiExtraction"]["id"] = 2
    assert fingerprint_generation_basis(input_snapshot=input_changed, **args) != first
