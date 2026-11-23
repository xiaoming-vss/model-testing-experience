import unittest

from testing_agent.core.config import Settings
from testing_agent.core.secrets import validate_runtime_secrets


def strong_settings(**overrides):
    values = {
        "env": "test",
        "http_host": "127.0.0.1",
        "http_port": 8000,
        "jwt_key": "j" * 32,
        "integration_key": "i" * 32,
        "worker_key": "w" * 32,
        "database_url": "sqlite+aiosqlite:///:memory:",
    }
    values.update(overrides)
    return Settings(**values)


class RuntimeSecretValidationTests(unittest.TestCase):
    def test_accepts_strong_keys(self):
        validate_runtime_secrets(strong_settings())

    def test_rejects_weak_jwt_key(self):
        with self.assertRaisesRegex(RuntimeError, "security.jwt.key"):
            validate_runtime_secrets(strong_settings(jwt_key="change-me"))

    def test_rejects_weak_integration_key(self):
        with self.assertRaisesRegex(RuntimeError, "security.integration.key"):
            validate_runtime_secrets(strong_settings(integration_key="change-me"))

    def test_rejects_weak_worker_key(self):
        with self.assertRaisesRegex(RuntimeError, "security.worker.key"):
            validate_runtime_secrets(strong_settings(worker_key="worker-token"))

    def test_rejects_short_worker_key(self):
        with self.assertRaisesRegex(RuntimeError, "security.worker.key"):
            validate_runtime_secrets(strong_settings(worker_key="short"))

    def test_allows_optional_worker_keys_to_be_blank(self):
        validate_runtime_secrets(strong_settings(integration_worker_key="", perf_worker_key=""))

    def test_rejects_weak_optional_worker_key(self):
        with self.assertRaisesRegex(RuntimeError, "security.integration_worker.key"):
            validate_runtime_secrets(strong_settings(integration_worker_key="change-me"))


if __name__ == "__main__":
    unittest.main()
