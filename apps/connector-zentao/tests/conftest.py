import pytest
from fastapi.testclient import TestClient

from app import config as app_config


def pytest_configure(config: pytest.Config) -> None:
    """Select the committed example before test collection imports the application."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        app_config,
        "DEFAULT_CONFIG_PATH",
        app_config.PROJECT_ROOT / "config/zentao.example.toml",
    )
    app_config.load_config_data.cache_clear()
    app_config.get_settings.cache_clear()
    config.add_cleanup(monkeypatch.undo)


@pytest.fixture
def client() -> TestClient:
    from app.main import create_app

    return TestClient(create_app())
