"""Preview tokens bind actor, exact source and target without disclosing content."""

from dataclasses import replace

import pytest

from testing_agent.domain.generation_import_preview import (
    ImportPreviewBinding,
    issue_import_preview_token,
    validate_import_preview_token,
)

SECRET = "test-only-preview-signing-key-32-bytes"


def binding():
    return ImportPreviewBinding(
        actor_id="actor",
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        candidate_id="candidate",
        snapshot_id="snapshot",
        current_token="current",
        content_hash="content-hash",
        full_lineage_hash="lineage",
        target_id="",
        target_fingerprint="target-hash",
    )


def test_preview_requires_the_same_actor_source_target_and_unexpired_token():
    source = binding()
    token = issue_import_preview_token(source, secret=SECRET, now=100, ttl_seconds=30)
    assert "candidate" not in token and "target-hash" not in token
    assert validate_import_preview_token(token, source, secret=SECRET, now=129)
    assert not validate_import_preview_token(token, source, secret=SECRET, now=130)
    for change in (
        {"actor_id": "other"},
        {"candidate_id": "other"},
        {"snapshot_id": "other"},
        {"current_token": "other"},
        {"content_hash": "other"},
        {"full_lineage_hash": "other"},
        {"target_id": "other"},
        {"target_fingerprint": "other"},
    ):
        assert not validate_import_preview_token(
            token, replace(source, **change), secret=SECRET, now=101
        )
    assert not validate_import_preview_token(
        token, source, secret="another-test-only-key-at-least-32-bytes", now=101
    )
    assert not validate_import_preview_token(token + "x", source, secret=SECRET, now=101)
    assert not validate_import_preview_token("v1.bad.signature", source, secret=SECRET, now=101)


def test_weak_key_and_invalid_lifetime_fail_closed():
    with pytest.raises(ValueError, match="key"):
        issue_import_preview_token(binding(), secret="weak", now=100)
    with pytest.raises(ValueError, match="lifetime"):
        issue_import_preview_token(binding(), secret=SECRET, now=100, ttl_seconds=3601)
    with pytest.raises(ValueError, match="incomplete"):
        issue_import_preview_token(replace(binding(), actor_id=""), secret=SECRET, now=100)
