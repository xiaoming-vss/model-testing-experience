"""LDAP connection policy; directory-specific state rules require deployment verification."""

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LdapSettings(BaseModel):
    """Single LDAP configuration structure shared by runtime settings and admin input."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    # Admin output views omit the secret, so they must not re-require it on validation.
    require_bind_password: ClassVar[bool] = True

    enabled: bool = False
    server_url: str = Field(default="", max_length=2048)
    start_tls: bool = True
    allow_insecure_connection: bool = False
    tls_ca_file: str = Field(default="", max_length=2048)
    tls_ca_pem: str = Field(default="", max_length=65536)
    bind_dn: str = Field(default="", max_length=2048)
    bind_password: str = Field(default="", max_length=4096, repr=False)
    user_search_base: str = Field(default="", max_length=2048)
    user_search_filter: str = Field(default="(uid={username})", max_length=4096)
    access_group_dn: str = Field(default="", max_length=2048)
    username_attribute: str = "uid"
    email_attribute: str = "mail"
    external_id_attribute: str = "entryUUID"
    group_member_attribute: str = "memberUid"
    group_member_value_type: str = "username"
    timeout_seconds: int = Field(default=5, ge=1, le=60)
    login_timeout_seconds: int = Field(default=30, ge=1, le=300)
    reconcile_interval_seconds: int = Field(default=300, ge=1, le=86400)
    auto_link_by_username: bool = False
    token_expire_hours: int = Field(default=12, ge=1, le=8760)
    # Set only after verifying service-account ACLs and real Synology lifecycle states.
    directory_rules_verified: bool = False
    active_user_filter: str = Field(default="", max_length=4096)
    disabled_user_filter: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def validate_policy(self) -> LdapSettings:
        if not self.enabled:
            return self
        for name in (
            "server_url",
            "bind_dn",
            "bind_password",
            "user_search_base",
            "access_group_dn",
        ):
            if name == "bind_password" and not type(self).require_bind_password:
                continue
            value = getattr(self, name)
            if hasattr(value, "get_secret_value"):
                value = value.get_secret_value()
            if not str(value or "").strip():
                raise ValueError(f"{name} is required when enabled")
        try:
            url = urlsplit(self.server_url)
            valid_port = url.port is None or 1 <= url.port <= 65535
        except ValueError:
            raise ValueError("server_url is invalid") from None
        if (
            url.scheme not in {"ldap", "ldaps"}
            or not url.hostname
            or not valid_port
            or url.username is not None
            or url.password is not None
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError("server_url must contain only LDAP host and port")
        if url.scheme == "ldaps" and self.start_tls:
            raise ValueError("start_tls cannot be combined with ldaps")
        if url.scheme == "ldap" and not self.start_tls and not self.allow_insecure_connection:
            raise ValueError("Plain LDAP requires explicit allow_insecure_connection")
        if self.user_search_filter.count("{username}") != 1:
            raise ValueError("user_search_filter requires one {username}")
        remainder = self.user_search_filter.replace("{username}", "")
        if "{" in remainder or "}" in remainder:
            raise ValueError("user_search_filter contains unknown placeholders")
        for name in (
            "username_attribute",
            "email_attribute",
            "external_id_attribute",
            "group_member_attribute",
        ):
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", getattr(self, name)):
                raise ValueError(f"{name} must be an LDAP attribute name")
        if (self.group_member_attribute.lower(), self.group_member_value_type) not in {
            ("memberuid", "username"),
            ("member", "dn"),
        }:
            raise ValueError("LDAP direct membership requires memberUid/username or member/dn")
        return self
