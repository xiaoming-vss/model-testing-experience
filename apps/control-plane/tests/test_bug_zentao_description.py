"""正文同步摘要：状态与提示文案。"""

from types import SimpleNamespace

from testing_agent.services.bug_zentao_description import description_summary, source_hash


def push(status, snapshot):
    return SimpleNamespace(description_status=status, description_sync_json=snapshot)


def bug(html="<p>正文</p>"):
    return SimpleNamespace(description_html=html)


def test_edited_local_description_returns_pending_before_resync():
    fields = description_summary(
        bug("<p>新正文</p>"), push("succeeded", {"sourceHash": source_hash("<p>旧正文</p>")})
    )
    assert fields["description_status"] == "pending"
    assert fields["error_message"] == "Bug 已创建，正文图片尚未同步，可再次推送补齐"


def test_failed_description_sync_reports_retryable_error():
    fields = description_summary(
        bug(), push("failed", {"errorMessage": "描述正文已变更，请核对两端描述后再同步图片"})
    )
    assert fields["description_status"] == "failed"
    assert fields["error_message"] == (
        "Bug 已创建，正文图片同步失败，可再次推送；描述正文已变更，请核对两端描述后再同步图片"
    )


def test_successful_sync_stays_quiet():
    fields = description_summary(
        bug(),
        push(
            "succeeded",
            {"sourceHash": source_hash("<p>正文</p>"), "overwrote": {"localEdited": True}},
        ),
    )
    assert fields == {"description_status": "succeeded"}


def imported_push():
    return SimpleNamespace(
        description_status="none",
        description_sync_json={},
        description_updated_at=None,
        source="import",
    )


def test_imported_bug_with_pulled_images_stays_quiet():
    html = '<p>正文</p><img data-file-id="f1">'
    fields = description_summary(
        bug(html), imported_push(), imported_local_digest=source_hash(html)
    )
    assert fields == {"description_status": "succeeded"}


def test_imported_bug_without_baseline_reports_pull_not_push():
    fields = description_summary(bug('<img data-file-id="f1">'), imported_push())
    assert fields["description_status"] == "pending"
    assert fields["error_message"] == "Bug 已创建，正文图片未全部从禅道补齐，可再次从禅道同步"


def test_imported_bug_edited_locally_still_asks_for_push():
    fields = description_summary(
        bug('<p>新正文</p><img data-file-id="f1">'),
        imported_push(),
        imported_local_digest=source_hash("<p>旧正文</p>"),
    )
    assert fields["description_status"] == "pending"
    assert fields["error_message"] == "Bug 已创建，正文图片尚未同步，可再次推送补齐"
