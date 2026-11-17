from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import SecretStr
from support import (
    FAKE_VERSION,
    fake_error_body,
    fake_pass_body,
    fake_sleep_body,
    fake_threshold_body,
    make_compiled_plan,
    make_settings,
    write_fake_k6,
)

from testing_agent_perf_worker.core.errors import ExecutionError
from testing_agent_perf_worker.runner.k6 import K6Runner
from testing_agent_perf_worker.runner.workspace import Workspace


def _workspace(tmp_path: Path) -> Workspace:
    return Workspace.create(tmp_path / "runs", "run-001")


async def test_runner_passes_and_reads_summary(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-pass.py", fake_pass_body())
    settings = make_settings(tmp_path, fake)
    workspace = _workspace(tmp_path)
    compiled = make_compiled_plan(workspace)

    execution = await K6Runner(settings).run(compiled, workspace)

    assert execution.exit_code == 0
    assert execution.stopped is False
    assert execution.timed_out is False
    assert execution.summary_missing is False
    assert execution.k6_version == FAKE_VERSION
    assert execution.summary is not None
    assert execution.summary["metrics"]["http_reqs"]["values"]["count"] == 1


async def test_runner_maps_threshold_exit_code(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-threshold.py", fake_threshold_body())
    settings = make_settings(tmp_path, fake)
    workspace = _workspace(tmp_path)

    execution = await K6Runner(settings).run(make_compiled_plan(workspace), workspace)

    assert execution.exit_code == 99
    assert execution.summary_missing is False
    assert execution.error_message == ""


async def test_runner_reports_execution_error(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-error.py", fake_error_body())
    settings = make_settings(tmp_path, fake)
    workspace = _workspace(tmp_path)

    execution = await K6Runner(settings).run(make_compiled_plan(workspace), workspace)

    assert execution.exit_code == 1
    assert execution.summary_missing is True
    assert "boom" in execution.error_message
    assert "boom" in execution.log_tail


async def test_runner_builds_minimal_environment(tmp_path: Path) -> None:
    recording = """
Path("argv.json").write_text(json.dumps(sys.argv))
env = {
    key: value
    for key, value in os.environ.items()
    if key.startswith("K6_") or key in {"tenant", "HOME", "PWD", "TMPDIR"}
}
Path("env.json").write_text(json.dumps(env))
Path("summary.json").write_text(json.dumps({"metrics": {}}))
sys.exit(0)
"""
    fake = write_fake_k6(tmp_path, "fake-record.py", recording)
    settings = make_settings(tmp_path, fake)
    settings.control_plane.worker_token = SecretStr("cp-secret")
    workspace = _workspace(tmp_path)

    await K6Runner(settings).run(make_compiled_plan(workspace), workspace)

    argv = json.loads((workspace.root / "argv.json").read_text(encoding="utf-8"))
    env = json.loads((workspace.root / "env.json").read_text(encoding="utf-8"))
    assert "run" in argv
    assert "--out" in argv
    assert "experimental-prometheus-rw" in argv
    assert "main.js" in argv
    assert env["K6_PROMETHEUS_RW_USERNAME"] == "writer"
    assert env["K6_PROMETHEUS_RW_PASSWORD"] == "rw-secret"
    assert env["tenant"] == "tenant-secret"
    assert "cp-secret" not in json.dumps(env)


async def test_runner_redacts_secrets_from_logs(tmp_path: Path) -> None:
    logging_body = """
print("password=" + os.environ.get("K6_PROMETHEUS_RW_PASSWORD", ""), file=sys.stderr, flush=True)
print("tenant=" + os.environ.get("tenant", ""), file=sys.stderr, flush=True)
Path("summary.json").write_text(json.dumps({"metrics": {}}))
sys.exit(0)
"""
    fake = write_fake_k6(tmp_path, "fake-log.py", logging_body)
    settings = make_settings(tmp_path, fake)
    workspace = _workspace(tmp_path)

    execution = await K6Runner(settings).run(make_compiled_plan(workspace), workspace)

    log_text = workspace.log_path.read_text(encoding="utf-8")
    assert "rw-secret" not in log_text
    assert "tenant-secret" not in log_text
    assert "***" in log_text
    assert "rw-secret" not in execution.log_tail
    assert "tenant-secret" not in execution.log_tail


async def test_runner_stops_process_group(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-sleep.py", fake_sleep_body())
    settings = make_settings(tmp_path, fake)
    workspace = _workspace(tmp_path)
    compiled = make_compiled_plan(workspace, max_duration_seconds=30, stop_grace_seconds=1)
    stop_event = asyncio.Event()

    task = asyncio.create_task(K6Runner(settings).run(compiled, workspace, stop_event))
    await asyncio.sleep(0.5)
    stop_event.set()
    execution = await asyncio.wait_for(task, timeout=10)

    assert execution.stopped is True
    assert execution.timed_out is False
    assert execution.duration_ms < 8000


async def test_runner_enforces_max_duration(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-sleep.py", fake_sleep_body())
    settings = make_settings(tmp_path, fake)
    workspace = _workspace(tmp_path)
    compiled = make_compiled_plan(workspace, max_duration_seconds=1, stop_grace_seconds=1)

    execution = await asyncio.wait_for(K6Runner(settings).run(compiled, workspace), timeout=10)

    assert execution.timed_out is True
    assert execution.stopped is False
    assert execution.duration_ms >= 900


async def test_runner_rejects_version_mismatch(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-v9.py", fake_pass_body(), version="9.9.9")
    settings = make_settings(tmp_path, fake)

    with pytest.raises(ExecutionError, match="版本不匹配"):
        await K6Runner(settings).check_version()


async def test_runner_rejects_missing_binary(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, tmp_path / "missing-k6")
    settings.k6.binary = str(tmp_path / "missing-k6")

    with pytest.raises(ExecutionError):
        await K6Runner(settings).check_version()


async def test_runner_rejects_preset_stop(tmp_path: Path) -> None:
    fake = write_fake_k6(tmp_path, "fake-pass.py", fake_pass_body())
    settings = make_settings(tmp_path, fake)
    workspace = _workspace(tmp_path)
    stop_event = asyncio.Event()
    stop_event.set()

    with pytest.raises(ExecutionError, match="启动前已停止"):
        await K6Runner(settings).run(make_compiled_plan(workspace), workspace, stop_event)
