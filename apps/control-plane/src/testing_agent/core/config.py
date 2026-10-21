from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from testing_agent.core.import_limits import ImportLimits
from testing_agent.core.ldap_config import LdapSettings
from testing_agent.core.object_storage import ObjectStorageSettings


@dataclass(frozen=True, slots=True)
class IntegrationExecutionSettings:
    enabled: bool = False
    project_ids: tuple[str, ...] = ()
    all_projects: bool = False
    accept_submissions: bool = True
    claim_enabled: bool = True
    lease_seconds: int = 60
    runtime_generation: str = ""
    succeeded_retention_days: int = 30
    failed_retention_days: int = 90
    claim_receipt_retention_days: int = 14
    maintenance_batch_size: int = 100
    restore_review_max_age_seconds: int = 3600
    worker_presence_ttl_seconds: int = 120

    def __post_init__(self):
        for name in ("enabled", "all_projects", "accept_submissions", "claim_enabled"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"integration_execution.{name} must be a boolean")
        if type(self.lease_seconds) is not int or not 10 <= self.lease_seconds <= 600:
            raise ValueError("integration_execution.lease_seconds must be between 10 and 600")
        if any(not isinstance(value, str) or not value for value in self.project_ids):
            raise ValueError("integration_execution.project_ids must contain nonempty strings")
        if self.enabled and not self.runtime_generation:
            raise ValueError("Enabled integration execution requires runtime_generation")
        for name, maximum in (
            ("succeeded_retention_days", 3650),
            ("failed_retention_days", 3650),
            ("claim_receipt_retention_days", 3650),
            ("maintenance_batch_size", 1000),
            ("restore_review_max_age_seconds", 86400),
        ):
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= maximum:
                raise ValueError(f"integration_execution.{name} must be between 1 and {maximum}")
        if (
            type(self.worker_presence_ttl_seconds) is not int
            or not 10 <= self.worker_presence_ttl_seconds <= 3600
        ):
            raise ValueError("integration_execution.worker_presence_ttl_seconds must be 10..3600")

    def uses_worker(self, project_id: str) -> bool:
        return self.enabled and (self.all_projects or project_id in self.project_ids)


@dataclass(frozen=True, slots=True)
class SuperAdminSettings:
    username: str = ""
    email: str = ""
    initial_password: str = "mtx123456"

    @property
    def configured(self) -> bool:
        return bool(self.username.strip() and self.email.strip())

    def __post_init__(self):
        for name in ("username", "email", "initial_password"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"security.super_admin.{name} must be a string")


@dataclass(frozen=True, slots=True)
class LoginSecuritySettings:
    max_failures: int = 5
    lock_minutes: int = 15
    rate_limit_window_minutes: int = 15

    def __post_init__(self):
        for name, maximum in (
            ("max_failures", 100),
            ("lock_minutes", 1440),
            ("rate_limit_window_minutes", 1440),
        ):
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= maximum:
                raise ValueError(f"security.login.{name} must be between 1 and {maximum}")


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
    uploads_dir: str  # Deprecated configuration compatibility; no business file IO.
    s3: ObjectStorageSettings = ObjectStorageSettings()
    code_overview_cache_ttl_seconds: int = 300
    integration_worker_key: str = ""
    integration_execution: IntegrationExecutionSettings = IntegrationExecutionSettings()
    jwt_user_expire_hours: int = 72
    jwt_super_admin_expire_hours: int = 24
    super_admin: SuperAdminSettings = SuperAdminSettings()
    login_security: LoginSecuritySettings = LoginSecuritySettings()
    ldap: LdapSettings = LdapSettings()
    asset_import: ImportLimits = ImportLimits()

    def __post_init__(self):
        if self.integration_worker_key and self.integration_worker_key == self.worker_key:
            raise ValueError(
                "Integration Worker credentials must differ from existing Worker credentials"
            )
        if self.integration_execution.enabled and not self.integration_worker_key:
            raise ValueError("Enabled integration execution requires a dedicated Worker key")
        for name in ("jwt_user_expire_hours", "jwt_super_admin_expire_hours"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 24 * 365:
                raise ValueError(f"security.jwt.{name} must be between 1 and 8760")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Settings:
        security = data.get("security", {})
        execution = dict(data.get("integration_execution", {}))
        project_ids = execution.get("project_ids", [])
        if not isinstance(project_ids, (list, tuple)):
            raise ValueError("integration_execution.project_ids must be a list")
        execution["project_ids"] = tuple(project_ids)
        jwt = security.get("jwt", {})
        return cls(
            asset_import=ImportLimits(**data.get("asset_import", {})),
            integration_worker_key=security.get("integration_worker", {}).get("key", ""),
            integration_execution=IntegrationExecutionSettings(**execution),
            s3=ObjectStorageSettings(**data.get("storage", {}).get("s3", {})),
            env=data.get("env", "local"),
            http_host=data.get("http", {}).get("host", "127.0.0.1"),
            http_port=int(data.get("http", {}).get("port", 8000)),
            jwt_key=jwt.get("key", "change-me"),
            jwt_expire_hours=int(jwt.get("expire_hours", 168)),
            jwt_user_expire_hours=int(jwt.get("user_expire_hours", 72)),
            jwt_super_admin_expire_hours=int(jwt.get("super_admin_expire_hours", 24)),
            super_admin=SuperAdminSettings(**security.get("super_admin", {})),
            login_security=LoginSecuritySettings(**security.get("login", {})),
            ldap=LdapSettings(),  # LDAP is configured exclusively through the database.
            integration_key=security.get("integration", {}).get("key", "change-me"),
            worker_key=security.get("worker", {}).get("key", ""),
            database_url=data.get("data", {}).get("db", {}).get("user", {}).get("dsn", ""),
            uploads_dir=data.get("storage", {}).get("uploads_dir", ""),
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
