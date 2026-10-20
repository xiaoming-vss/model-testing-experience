"""Database-managed LDAP configuration, safe serialization and atomic activation."""

import ssl
from dataclasses import asdict, replace
from typing import Any

from testing_agent.core.config import Settings
from testing_agent.core.errors import AppError, ErrForbidden, ErrLdapUnavailable
from testing_agent.core.ldap_config import LdapSettings
from testing_agent.core.ldap_directory import LdapDirectory
from testing_agent.domain.ldap_identity import DirectoryUnavailable
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher


def decode_ldap(data: dict[str, Any], settings: Settings) -> LdapSettings:
    values = dict(data)
    encrypted = values.pop("bind_password_encrypted", "")
    values["bind_password"] = (
        IntegrationCredentialCipher(settings.integration_key).decrypt(encrypted)
        if encrypted
        else ""
    )
    return LdapSettings(**values)


async def effective_settings(runtime: AuthRuntimeRepository, settings: Settings) -> Settings:
    row = await runtime.get()
    if row is None:
        raise ErrLdapUnavailable()
    if row.ldap_config is None:
        if row.mode != "local":
            raise ErrLdapUnavailable()
        return replace(settings, ldap=LdapSettings())
    try:
        return replace(settings, ldap=decode_ldap(row.ldap_config, settings))
    except (ValueError, TypeError):
        raise ErrLdapUnavailable() from None


class LdapSettingsService:
    def __init__(self, runtime: AuthRuntimeRepository, bootstrap: Settings):
        self.runtime = runtime
        self.bootstrap = bootstrap

    async def _authorize(self, actor_id: str) -> None:
        user = await UserRepository(self.runtime.session).get_by_user_id(actor_id)
        if user is None or not user.is_super_admin or user.status != "active":
            raise ErrForbidden()

    async def read(self, actor_id: str) -> dict:
        await self._authorize(actor_id)
        row = await self.runtime.get()
        if row is None:
            raise ErrLdapUnavailable()
        values = dict(row.ldap_config) if row.ldap_config is not None else asdict(LdapSettings())
        password = values.pop("bind_password", "")
        encrypted = values.pop("bind_password_encrypted", "")
        return {
            "generation": row.generation,
            "source": "database",
            "passwordConfigured": bool(password or encrypted),
            "config": values,
        }

    async def _candidate(self, values: dict[str, Any], clear_password: bool) -> LdapSettings:
        row = await self.runtime.get()
        data = (
            dict(row.ldap_config) if row and row.ldap_config is not None else asdict(LdapSettings())
        )
        encrypted = data.pop("bind_password_encrypted", "")
        incoming = dict(values)
        secret = incoming.pop("bind_password", None)
        if encrypted and not clear_password and not secret:
            try:
                data["bind_password"] = IntegrationCredentialCipher(
                    self.bootstrap.integration_key
                ).decrypt(encrypted)
            except ValueError:
                raise AppError(1033, "无法读取已保存密码，请重新输入查询密码后保存", 400) from None
        data.setdefault("bind_password", "")
        data.update(incoming)
        if clear_password:
            data["bind_password"] = ""
        elif secret:
            data["bind_password"] = secret
        try:
            config = LdapSettings(**data)
            if config.tls_ca_pem:
                if "PRIVATE KEY" in config.tls_ca_pem:
                    raise ValueError("CA must not contain private keys")
                ssl.create_default_context(cadata=config.tls_ca_pem)
            if config.enabled and (
                not config.directory_rules_verified
                or not config.active_user_filter
                or not config.disabled_user_filter
            ):
                raise ValueError("启用前请填写并确认目录状态规则")
            return config
        except (ValueError, TypeError, ssl.SSLError):
            # Settings validation messages contain names/rules, never supplied secret values.
            raise AppError(
                1030, "LDAP 配置无效，请检查必填字段、连接方式和目录状态规则", 400
            ) from None

    async def save(
        self, actor_id: str, generation: int, values: dict[str, Any], clear_password: bool = False
    ) -> dict:
        await self._authorize(actor_id)
        try:
            row = await self.runtime.get(for_update=True)
            if row is None or row.generation != generation:
                raise AppError(1031, "LDAP 配置已被更新，请刷新后重试", 409)
            candidate = await self._candidate(values, clear_password)
            encoded = asdict(candidate)
            secret = encoded.pop("bind_password")
            encoded["bind_password_encrypted"] = (
                IntegrationCredentialCipher(self.bootstrap.integration_key).encrypt(secret)
                if secret
                else ""
            )
            changed = await AuthModeService(
                self.runtime, replace(self.bootstrap, ldap=candidate)
            ).apply_locked(row)
            if not changed:
                row.generation += 1  # Includes draft edits while LDAP is disabled.
            row.ldap_config = encoded
            await self.runtime.commit()
        except Exception:
            await self.runtime.rollback()
            raise
        return await self.read(actor_id)

    async def test(
        self,
        actor_id: str,
        values: dict[str, Any],
        username: str = "",
        clear_password: bool = False,
    ) -> dict:
        await self._authorize(actor_id)
        config = await self._candidate({**values, "enabled": False}, clear_password)
        try:
            config = replace(config, enabled=True)
        except ValueError:
            raise AppError(1030, "连接检查需要地址、查询账号密码、搜索范围和访问组", 400) from None
        await self.runtime.rollback()  # No DB locks/transactions during external IO.
        directory = LdapDirectory(config)
        try:
            await directory.check_connection()
            if username:
                identity = await directory.lookup(username.strip())
                return {
                    "connected": True,
                    "userFound": identity is not None,
                    "eligible": bool(identity and identity.eligible),
                    "emailPresent": bool(identity and identity.emails),
                    "message": "查询与访问资格检查完成；未验证用户密码，未保存配置",
                }
            return {
                "connected": True,
                "message": "查询账号、搜索范围和访问组检查通过；未验证用户密码，未保存配置",
            }
        except DirectoryUnavailable:
            raise ErrLdapUnavailable() from None
