from pathlib import Path

import pytest
from pydantic import ValidationError

from testing_agent_integration_worker.core.config import Settings, load_settings


def test_separate_config_and_secrets_are_not_in_repr(tmp_path, monkeypatch):
    path = tmp_path / "worker.toml"
    path.write_text('[control_plane]\nbase_url="http://cp.test"\nworker_token="private-token"\n')
    monkeypatch.setenv("APP_CONF", str(path))
    settings = load_settings()
    assert settings.control_plane.worker_token.get_secret_value() == "private-token"
    assert "private-token" not in repr(settings)
    assert settings.worker.health_file == Path("runtime/health.json")


@pytest.mark.parametrize("bad", ["", "GENERATE", "change-me"])
def test_missing_or_placeholder_worker_key_fails_startup(bad):
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {"control_plane": {"base_url": "http://cp.test", "worker_token": bad}}
        )


def test_cli_path_precedes_environment(tmp_path, monkeypatch):
    path = tmp_path / "explicit.toml"
    path.write_text('[control_plane]\nbase_url="http://cp.test"\nworker_token="key"\n')
    monkeypatch.setenv("APP_CONF", str(tmp_path / "missing.toml"))
    assert load_settings(path).control_plane.base_url == "http://cp.test"
