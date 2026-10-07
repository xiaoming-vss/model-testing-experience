import os
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ControlPlaneSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str
    worker_token: SecretStr
    timeout_seconds: float = Field(default=15, gt=0, le=120)
    retry_attempts: int = Field(default=3, ge=1, le=5)

    @field_validator("base_url")
    @classmethod
    def url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Control-plane URL must be an HTTP origin without credentials")
        return value.rstrip("/")

    @field_validator("worker_token")
    @classmethod
    def token(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value().strip() in {"", "GENERATE", "change-me"}:
            raise ValueError("A dedicated integration Worker token is required")
        return value


class WorkerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    poll_interval_seconds: float = Field(default=2, gt=0, le=60)
    heartbeat_interval_seconds: float = Field(default=10, gt=0, le=30)
    lease_margin_seconds: float = Field(default=2, ge=0, le=5)
    shutdown_grace_seconds: float = Field(default=210, gt=0, le=300)
    health_file: Path = Path("runtime/health.json")
    evidence_file: Path = Path("runtime/evidence.json")
    health_max_age_seconds: float = Field(default=90, ge=30, le=300)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    control_plane: ControlPlaneSettings
    worker: WorkerSettings = Field(default_factory=WorkerSettings)


def load_settings(path: str | Path | None = None) -> Settings:
    selected = Path(path or os.environ.get("APP_CONF") or "config/local.toml")
    with selected.open("rb") as stream:
        return Settings.model_validate(tomllib.load(stream))
