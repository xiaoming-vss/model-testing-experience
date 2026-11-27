import sys
from pathlib import Path

import pytest

from testing_agent_integration_worker import main


def _argv(monkeypatch: pytest.MonkeyPatch, config: Path, *, healthcheck: bool) -> None:
    argv = ["integration-worker", "--config", str(config)]
    if healthcheck:
        argv.append("--healthcheck")
    monkeypatch.setattr(sys, "argv", argv)


def test_healthcheck_exits_1_when_the_configuration_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # The probe contract is 0 for healthy and 1 otherwise, whatever the reason.
    _argv(monkeypatch, tmp_path / "missing.toml", healthcheck=True)

    with pytest.raises(SystemExit) as caught:
        main.main()

    assert caught.value.code == 1


def test_healthcheck_exits_1_when_the_configuration_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = tmp_path / "worker.toml"
    config.write_text('[control_plane]\nbase_url="http://cp.test"\nworker_token=""\n')
    _argv(monkeypatch, config, healthcheck=True)

    with pytest.raises(SystemExit) as caught:
        main.main()

    assert caught.value.code == 1


def test_invalid_configuration_still_exits_2_outside_the_healthcheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # A configuration error stays distinguishable from a runtime failure.
    _argv(monkeypatch, tmp_path / "missing.toml", healthcheck=False)

    with pytest.raises(SystemExit) as caught:
        main.main()

    assert caught.value.code == 2
