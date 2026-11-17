from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest
from support import (
    FIXTURES,
    base_spec_dict,
    fake_pass_body,
    fake_threshold_body,
    make_settings,
    write_fake_k6,
)

from testing_agent_perf_worker.app import run_once
from testing_agent_perf_worker.contracts.result import RunOutcome, RunStatus
from testing_agent_perf_worker.main import main


def _write_config(
    tmp_path: Path,
    fake_k6: Path,
    *,
    mode: str = "once",
    snapshot_file: str = str(FIXTURES / "case.yaml"),
) -> Path:
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
mode = "{mode}"

[worker]
health_file = "{tmp_path / "health.json"}"

[k6]
binary = "{fake_k6}"

[runner]
workspace_root = "{tmp_path / "runs"}"

[once]
snapshot_file = "{snapshot_file}"
""",
        encoding="utf-8",
    )
    return config


def test_run_once_completes(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-pass.py", fake_pass_body())
    settings = make_settings(tmp_path, fake)

    result = asyncio.run(run_once(settings, FIXTURES / "case.yaml"))

    workspace = Path(settings.runner.workspace_root) / "fixture-run-001"
    assert result.status is RunStatus.COMPLETED
    assert result.outcome is RunOutcome.PASSED
    assert result.summary is not None
    assert (workspace / "result.json").is_file()
    assert (workspace / "plan.json").is_file()
    assert (workspace / "main.js").is_file()
    assert (workspace / "data" / "users.json").is_file()
    assert (workspace / "summary.json").stat().st_mode & 0o777 == 0o600


def test_run_once_reports_threshold_failure(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-threshold.py", fake_threshold_body())
    settings = make_settings(tmp_path, fake)

    result = asyncio.run(run_once(settings, FIXTURES / "case.yaml"))

    assert result.status is RunStatus.COMPLETED
    assert result.outcome is RunOutcome.THRESHOLD_FAILED
    assert result.exit_code == 99


def test_run_once_without_criteria_is_inconclusive(tmp_path: Path) -> None:
    spec_data = base_spec_dict()
    spec_data["case"]["acceptance"] = {
        "source": "missing",
        "confirmed": False,
        "criteria": {},
    }
    spec_path = tmp_path / "case.json"
    spec_path.write_text(json.dumps(spec_data), encoding="utf-8")
    fake = write_fake_k6(tmp_path, "fake-pass.py", fake_pass_body())
    settings = make_settings(tmp_path, fake)

    result = asyncio.run(run_once(settings, spec_path))

    assert result.status is RunStatus.COMPLETED
    assert result.outcome is RunOutcome.INCONCLUSIVE


def test_main_once_prints_result(tmp_path: Path, capsys: object) -> None:
    fake = write_fake_k6(tmp_path, "fake-pass.py", fake_pass_body())
    config = _write_config(tmp_path, fake)

    exit_code = main(["--config", str(config)])

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 0
    assert '"runId": "fixture-run-001"' in captured.out
    assert '"completed"' in captured.out


def test_main_poll_requires_control_plane_config(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake = write_fake_k6(tmp_path, "fake-pass.py", fake_pass_body())
    config = _write_config(tmp_path, fake, mode="poll")

    with caplog.at_level(logging.ERROR):
        exit_code = main(["--config", str(config)])

    assert exit_code == 1
    assert "control_plane" in caplog.text


def test_main_requires_snapshot_file(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-pass.py", fake_pass_body())
    config = _write_config(tmp_path, fake, snapshot_file="")

    exit_code = main(["--config", str(config)])

    assert exit_code == 1
