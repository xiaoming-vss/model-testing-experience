"""Approved UI import payloads shared by tests; no collected cases."""

from datetime import UTC, datetime
from types import SimpleNamespace


def approved_ui_run():
    return SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        # The old import route remains available for standalone historical runs.
        requirement_id="",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        checkpoint_enabled=False,
        current_stage="",
        stage_status="",
        snapshot_json={},
        error_message="",
        config_json={},
        result_yaml="""cases:
  - name: " login "
    enabled: false
    orderNo: 7
    stepsJson:
      - orderNo: 1
        stepName: Enter username
        keyword: fill
        locatorType: test_id
        locatorValue: username
        operationValue: alice
        continueOnFailure: true
        enabled: false
  - name: Health
    enabled: true
    orderNo: 8
    stepsJson:
      - orderNo: 1
        stepName: Open health
        keyword: open
        operationValue: https://example.test/health
        continueOnFailure: false
        enabled: true
""",
        result_summary_json={},
        review_status="approved",
        import_status="pending",
        imported_targets=[],
        imported_at=None,
        reviewer_user_id="user-1",
        reviewed_at=datetime.now(UTC),
        review_comment="ready",
        duration_ms=0,
    )
