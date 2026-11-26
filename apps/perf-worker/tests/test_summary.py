from __future__ import annotations

import json
from pathlib import Path

from support import FIXTURES

from testing_agent_perf_worker.runner.summary import compact_summary, read_summary


def test_compact_summary_keeps_metrics_only() -> None:
    raw = json.loads((FIXTURES / "summary.json").read_text(encoding="utf-8"))

    compact = compact_summary(raw)

    assert "metrics" in compact
    assert "root_group" not in compact
    assert compact["metrics"]["http_req_duration"]["values"]["p(95)"] == 19.0
    assert compact["metrics"]["http_req_duration"]["thresholds"]["p(95)<500"] == {"ok": True}


def test_read_summary_missing(tmp_path: Path) -> None:
    summary, missing, reason = read_summary(tmp_path / "missing.json", 5)

    assert summary is None
    assert missing is True
    # k6 wrote nothing; there is no defect to explain.
    assert reason == ""


def test_read_summary_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_text("{", encoding="utf-8")

    summary, missing, reason = read_summary(path, 5)

    assert summary is None
    assert missing is True
    assert reason == "k6 摘要不是合法 JSON，已忽略"


def test_read_summary_too_large(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_text(json.dumps({"metrics": {}}), encoding="utf-8")

    summary, missing, reason = read_summary(path, 1)
    assert summary is not None
    assert missing is False
    big = tmp_path / "big.json"
    big.write_bytes(b"{" + b" " * (1024 * 1024 + 1) + b"}")
    summary, missing, reason = read_summary(big, 1)
    assert summary is None
    assert missing is True
    assert reason == "k6 摘要超过 1MB 上限，已忽略"


def test_read_summary_rejects_a_non_object(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_text("[1, 2]", encoding="utf-8")

    summary, missing, reason = read_summary(path, 5)

    assert (summary, missing, reason) == (None, True, "k6 摘要不是 JSON 对象，已忽略")


def test_unusable_summary_reason_reaches_the_result(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from support import base_spec_dict, make_compiled_plan

    from testing_agent_perf_worker.app import build_result
    from testing_agent_perf_worker.contracts.result import ResultFlag
    from testing_agent_perf_worker.contracts.spec import RunSpec
    from testing_agent_perf_worker.runner.k6 import K6Execution
    from testing_agent_perf_worker.runner.workspace import Workspace

    workspace = Workspace.create(tmp_path / "runs", "run-001")
    now = datetime.now(UTC)
    execution = K6Execution(
        exit_code=0,
        started_at=now,
        finished_at=now,
        duration_ms=5,
        summary=None,
        summary_missing=True,
        summary_error="k6 摘要超过 5MB 上限，已忽略",
        stopped=False,
        timed_out=False,
        k6_version="2.3.0",
        log_tail="",
        log_truncated=False,
    )

    result = build_result(
        RunSpec.model_validate(base_spec_dict()), make_compiled_plan(workspace), execution
    )

    # A passed run keeps its status; the user learns why the summary is absent.
    assert result.status.value == "completed"
    assert ResultFlag.SUMMARY_MISSING in result.flags
    assert result.error_message == "k6 摘要超过 5MB 上限，已忽略"
