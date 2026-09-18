import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_FILE = "config/zentao.toml"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / CONFIG_FILE


@dataclass(frozen=True)
class Settings:
    app_name: str = "zentao-service"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    enable_docs: bool = True
    log_level: str = "INFO"
    log_json: bool = False


def get_config_path() -> Path:
    return DEFAULT_CONFIG_PATH


@lru_cache
def load_config_data() -> dict[str, Any]:
    config_path = get_config_path()
    if not config_path.exists():
        return {}

    with config_path.open("rb") as file:
        return tomllib.load(file)


@lru_cache
def get_settings() -> Settings:
    config_path = get_config_path()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            "Create it from config/zentao.example.toml first."
        )

    service_data = load_config_data().get("service", {})
    if not isinstance(service_data, dict):
        service_data = {}

    return Settings(
        app_name=str(service_data.get("app_name", "zentao-service")).strip(),
        app_env=str(service_data.get("app_env", "local")).strip(),
        api_v1_prefix=str(service_data.get("api_v1_prefix", "/api/v1")).strip(),
        host=str(service_data.get("host", "0.0.0.0")).strip(),
        port=int(service_data.get("port", 8000)),
        enable_docs=bool(service_data.get("enable_docs", True)),
        log_level=str(service_data.get("log_level", "INFO")).strip(),
        log_json=bool(service_data.get("log_json", False)),
    )
