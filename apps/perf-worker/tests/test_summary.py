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
    summary, missing = read_summary(tmp_path / "missing.json", 5)

    assert summary is None
    assert missing is True


def test_read_summary_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_text("{", encoding="utf-8")

    summary, missing = read_summary(path, 5)

    assert summary is None
    assert missing is True


def test_read_summary_too_large(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_text(json.dumps({"metrics": {}}), encoding="utf-8")

    summary, missing = read_summary(path, 1)

    assert summary is not None
    assert missing is False
    big = tmp_path / "big.json"
    big.write_bytes(b"{" + b" " * (1024 * 1024 + 1) + b"}")
    summary, missing = read_summary(big, 1)
    assert summary is None
    assert missing is True
