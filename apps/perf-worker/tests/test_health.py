from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from testing_agent_perf_worker.worker.health import HealthFile


def test_progress_file_is_healthy_for_current_process(tmp_path: Path) -> None:
    health = HealthFile(tmp_path / "health.json", 90)

    health.progress("running")

    assert health.healthy() is True


def test_missing_health_file_is_unhealthy(tmp_path: Path) -> None:
    health = HealthFile(tmp_path / "missing.json", 90)

    assert health.healthy() is False


def test_corrupt_health_file_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    path.write_text("not-json", encoding="utf-8")
    health = HealthFile(path, 90)

    assert health.healthy() is False


def test_stale_health_file_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    payload = {
        "pid": os.getpid(),
        "stage": "running",
        "progressAt": (datetime.now(UTC) - timedelta(seconds=120)).isoformat(),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    health = HealthFile(path, 90)

    assert health.healthy() is False


def test_invalid_pid_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    payload = {
        "pid": 0,
        "stage": "running",
        "progressAt": datetime.now(UTC).isoformat(),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    health = HealthFile(path, 90)

    assert health.healthy() is False
