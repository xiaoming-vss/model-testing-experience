from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from test_worker.health import HealthServer, health_port_from_env


def test_healthz_returns_ok() -> None:
    server = HealthServer(host="127.0.0.1", port=0)
    server.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/healthz",
            timeout=2,
        ) as response:
            assert response.status == 200
            assert response.read() == b"ok\n"
    finally:
        server.stop()


def test_unknown_path_returns_404() -> None:
    server = HealthServer(host="127.0.0.1", port=0)
    server.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.port}/unknown",
                timeout=2,
            )
        assert caught.value.code == 404
    finally:
        server.stop()


def test_unset_port_env_disables_health_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_WORKER_HEALTH_PORT", raising=False)
    assert health_port_from_env() is None


def test_invalid_port_env_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_WORKER_HEALTH_PORT", "not-a-port")
    assert health_port_from_env() == 8080
