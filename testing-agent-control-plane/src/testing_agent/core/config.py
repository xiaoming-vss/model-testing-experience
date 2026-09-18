from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Settings:
    env: str
    http_host: str
    http_port: int
    jwt_key: str
    jwt_expire_hours: int
    integration_key: str
    worker_key: str
    database_url: str
    uploads_dir: str
    zentao_service_base_url: str = "http://127.0.0.1:8010"
    code_overview_cache_ttl_seconds: int = 300

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Settings:
        security = data.get("security", {})
        return cls(
            env=data.get("env", "local"),
            http_host=data.get("http", {}).get("host", "127.0.0.1"),
            http_port=int(data.get("http", {}).get("port", 8000)),
            jwt_key=security.get("jwt", {}).get("key", "change-me"),
            jwt_expire_hours=int(security.get("jwt", {}).get("expire_hours", 168)),
            integration_key=security.get("integration", {}).get("key", "change-me"),
            worker_key=security.get("worker", {}).get("key", ""),
            database_url=data.get("data", {}).get("db", {}).get("user", {}).get("dsn", ""),
            uploads_dir=data.get("storage", {}).get(
                "uploads_dir", "storage/ai-generate-task-sources"
            ),
            zentao_service_base_url=data.get("integrations", {})
            .get("zentao_service", {})
            .get("base_url", "http://127.0.0.1:8010"),
            code_overview_cache_ttl_seconds=int(
                data.get("code_overview", {}).get("cache_ttl_seconds", 300)
            ),
        )


def load_settings(path: str | os.PathLike[str] | None = None) -> Settings:
    config_path = Path(path or os.getenv("APP_CONF") or "config/local.toml")
    if config_path.exists():
        with config_path.open("rb") as fh:
            return Settings.from_mapping(tomllib.load(fh))
    return Settings.from_mapping({})


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
