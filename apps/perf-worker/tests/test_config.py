from __future__ import annotations

from pathlib import Path

import pytest

from testing_agent_perf_worker.core.config import Settings, load_settings
from testing_agent_perf_worker.core.errors import ConfigError


def _config_text(
    *,
    mode: str = "once",
    worker_token: str = "worker-token",
    workspace_root: str = "./runtime/runs",
    snapshot_file: str = "./case.yaml",
    health_age: int = 90,
) -> str:
    return f"""
mode = "{mode}"

[control_plane]
base_url = "http://127.0.0.1:19000"
worker_token = "{worker_token}"

[worker]
health_file = "./runtime/health.json"
health_max_age_seconds = {health_age}

[k6]
binary = "/usr/bin/k6"
expected_version = "2.3.0"

[runner]
workspace_root = "{workspace_root}"
max_duration_seconds = 120
stop_grace_seconds = 10
max_data_file_mb = 8
max_summary_mb = 4

[once]
snapshot_file = "{snapshot_file}"
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_are_local_once_configuration() -> None:
    settings = Settings()
    assert settings.mode == "once"
    assert settings.k6.binary == "k6"
    assert settings.k6.expected_version == "2.3.0"
    assert settings.runner.workspace_root == "./runtime/runs"
    assert settings.worker.health_file == "./runtime/health.json"
    assert not hasattr(settings.runner, "keep_failed_workspace_hours")


def test_load_resolves_relative_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_CONF", raising=False)
    config = _write(tmp_path / "config.toml", _config_text())

    settings = load_settings(config)

    assert settings.mode == "once"
    assert Path(settings.worker.health_file) == (tmp_path / "runtime/health.json").resolve()
    assert Path(settings.runner.workspace_root) == (tmp_path / "runtime/runs").resolve()
    assert Path(settings.once.snapshot_file) == (tmp_path / "case.yaml").resolve()
    assert settings.runner.max_data_file_mb == 8
    assert settings.k6.expected_version == "2.3.0"


def test_app_conf_is_used_when_no_explicit_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write(tmp_path / "config.toml", _config_text())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_CONF", str(config))

    settings = load_settings()

    assert Path(settings.once.snapshot_file) == (tmp_path / "case.yaml").resolve()


def test_explicit_path_precedes_app_conf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    explicit = _write(tmp_path / "explicit.toml", _config_text(worker_token="explicit"))
    other = _write(tmp_path / "other.toml", _config_text(worker_token="other"))
    monkeypatch.setenv("APP_CONF", str(other))

    settings = load_settings(explicit)

    assert settings.control_plane.worker_token.get_secret_value() == "explicit"


def test_missing_config_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_CONF", raising=False)
    monkeypatch.setattr("testing_agent_perf_worker.core.config._project_root", lambda: tmp_path)

    with pytest.raises(ConfigError):
        load_settings()


def test_invalid_config_does_not_leak_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write(
        tmp_path / "config.toml",
        _config_text(mode="invalid", worker_token="super-secret-token"),
    )
    monkeypatch.delenv("APP_CONF", raising=False)

    with pytest.raises(ConfigError) as error:
        load_settings(config)

    assert "super-secret-token" not in str(error.value)


def test_invalid_health_age_raises(tmp_path: Path) -> None:
    config = _write(tmp_path / "config.toml", _config_text(health_age=10))

    with pytest.raises(ConfigError):
        load_settings(config)


def test_removed_workspace_retention_field_is_rejected(tmp_path: Path) -> None:
    text = _config_text().replace("[runner]\n", "[runner]\nkeep_failed_workspace_hours = 24\n")
    config = _write(tmp_path / "config.toml", text)

    with pytest.raises(ConfigError, match="keep_failed_workspace_hours"):
        load_settings(config)


def test_poll_mode_loads_but_is_selected_by_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write(tmp_path / "config.toml", _config_text(mode="poll"))
    monkeypatch.delenv("APP_CONF", raising=False)

    settings = load_settings(config)

    assert settings.mode == "poll"
