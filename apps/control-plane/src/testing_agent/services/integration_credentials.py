from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class IntegrationCredentialCipher:
    _PREFIX = "enc:v1:"
    _INSECURE_SECRETS = {"", "change-me", "replace-with-local-integration-key"}

    def __init__(self, secret: str):
        if secret.strip() in self._INSECURE_SECRETS:
            raise ValueError("必须配置安全的集成凭据加密密钥")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        encrypted = self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"{self._PREFIX}{encrypted}"

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext.startswith(self._PREFIX):
            raise ValueError("集成凭据无法解密")
        payload = ciphertext.removeprefix(self._PREFIX)
        try:
            return self._fernet.decrypt(payload.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as exc:
            raise ValueError("集成凭据无法解密") from exc
