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


def test_progress_replaces_the_file_atomically_and_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "health.json"
    health = HealthFile(path, 90)
    health.progress("polling")
    health.progress("running")

    # The probe only ever reads a complete file, and no half-written sibling lingers.
    assert sorted(item.name for item in path.parent.iterdir()) == ["health.json"]
    assert json.loads(path.read_text())["stage"] == "running"
    assert path.stat().st_mode & 0o777 == 0o600


def test_stop_removes_the_file(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    health = HealthFile(path, 90)
    health.progress("running")

    health.stop()

    assert not path.exists()
    assert health.healthy() is False
    # Stopping twice, as an exit path and a signal handler might, is harmless.
    health.stop()
