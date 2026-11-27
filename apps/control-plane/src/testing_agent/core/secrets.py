from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from testing_agent.core.config import Settings

INSECURE_SECRETS = {
    "change-me",
    "change_me",
    "changeme",
    "generate",
    "replace-with-local-integration-key",
    "mtx123456",
    "worker-token",
    "test-jwt",
    "test-integration",
    "password",
    "secret",
}

MIN_SECRET_LENGTH = 32
MIN_PASSWORD_LENGTH = 8


def is_placeholder(value: str) -> bool:
    """Tell whether a secret is one of the values committed as an example."""
    return value.strip().lower() in INSECURE_SECRETS


def password_is_insecure(value: str) -> bool:
    """Too short or a placeholder: the super admin must not be seeded with it.

    The repository scripts read this rule from the file so that every check a
    deployment goes through refuses the same passwords as the service itself.
    """
    password = value.strip()
    return len(password) < MIN_PASSWORD_LENGTH or is_placeholder(password)


def _validate_secret(name: str, value: str) -> None:
    normalized = value.strip()
    if len(normalized) < MIN_SECRET_LENGTH or is_placeholder(normalized):
        raise RuntimeError(
            f"{name} 必须配置安全密钥（至少 {MIN_SECRET_LENGTH} 个字符，且不能使用占位值）；"
            "运行 python3 scripts/manage.py upgrade-config 或修改 config/platform.toml"
        )


def validate_runtime_secrets(settings: Settings) -> None:
    _validate_secret("security.jwt.key", settings.jwt_key)
    _validate_secret("security.integration.key", settings.integration_key)
    _validate_secret("security.worker.key", settings.worker_key)
    for name, value in (
        ("security.integration_worker.key", settings.integration_worker_key),
        ("security.perf_worker.key", settings.perf_worker_key),
    ):
        if value.strip():
            _validate_secret(name, value)
