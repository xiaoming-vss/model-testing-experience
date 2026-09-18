from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.config import load_config_data


@dataclass(frozen=True)
class ZentaoTomlConfig:
    # Populated from the request, never loaded from TOML.
    base_url: str = ""
    timeout_seconds: int = 15
    verify_ssl: bool = True
    ca_file: str = ""

    @property
    def api_base_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/api.php/v2"):
            return base_url
        if base_url.endswith("/api.php"):
            return f"{base_url}/v2"
        return f"{base_url}/api.php/v2"


@lru_cache
def get_zentao_toml_config() -> ZentaoTomlConfig:
    raw_data = load_config_data()
    zentao_data = raw_data.get("zentao", {})
    if not isinstance(zentao_data, dict):
        zentao_data = {}
    timeout_seconds = int(zentao_data.get("timeout_seconds", 15))
    verify_ssl = _parse_bool(zentao_data.get("verify_ssl", True))

    return ZentaoTomlConfig(
        timeout_seconds=timeout_seconds,
        verify_ssl=verify_ssl,
        ca_file=str(zentao_data.get("ca_file", "")).strip(),
    )


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
