"""LDAP connection policy; directory-specific state rules require deployment verification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class LdapSettings:
    enabled: bool = False
    server_url: str = ""
    start_tls: bool = True
    allow_insecure_connection: bool = False
    tls_ca_file: str = ""
    tls_ca_pem: str = ""
    bind_dn: str = ""
    bind_password: str = field(default="", repr=False)
    user_search_base: str = ""
    user_search_filter: str = "(uid={username})"
    access_group_dn: str = ""
    username_attribute: str = "uid"
    email_attribute: str = "mail"
    external_id_attribute: str = "entryUUID"
    group_member_attribute: str = "memberUid"
    group_member_value_type: str = "username"
    timeout_seconds: int = 5
    login_timeout_seconds: int = 30
    reconcile_interval_seconds: int = 300
    auto_link_by_username: bool = False
    token_expire_hours: int = 12
    # Set only after verifying service-account ACLs and real Synology lifecycle states.
    directory_rules_verified: bool = False
    active_user_filter: str = ""
    disabled_user_filter: str = ""

    def __post_init__(self) -> None:
        for name in (
            "enabled",
            "start_tls",
            "allow_insecure_connection",
            "auto_link_by_username",
            "directory_rules_verified",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"security.ldap.{name} must be a boolean")
        for name in (
            "server_url",
            "tls_ca_file",
            "tls_ca_pem",
            "bind_dn",
            "bind_password",
            "user_search_base",
            "user_search_filter",
            "access_group_dn",
            "username_attribute",
            "email_attribute",
            "external_id_attribute",
            "group_member_attribute",
            "group_member_value_type",
            "active_user_filter",
            "disabled_user_filter",
        ):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"security.ldap.{name} must be a string")
        for name, maximum in (
            ("timeout_seconds", 60),
            ("login_timeout_seconds", 300),
            ("reconcile_interval_seconds", 86400),
            ("token_expire_hours", 8760),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"security.ldap.{name} must be between 1 and {maximum}")
        if not self.enabled:
            return
        for name in (
            "server_url",
            "bind_dn",
            "bind_password",
            "user_search_base",
            "access_group_dn",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"security.ldap.{name} is required when enabled")
        try:
            url = urlsplit(self.server_url)
            valid_port = url.port is None or 1 <= url.port <= 65535
        except ValueError:
            raise ValueError("security.ldap.server_url is invalid") from None
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
            raise ValueError("security.ldap.server_url must contain only LDAP host and port")
        if url.scheme == "ldaps" and self.start_tls:
            raise ValueError("security.ldap.start_tls cannot be combined with ldaps")
        if url.scheme == "ldap" and not self.start_tls and not self.allow_insecure_connection:
            raise ValueError("Plain LDAP requires explicit allow_insecure_connection")
        if self.user_search_filter.count("{username}") != 1:
            raise ValueError("security.ldap.user_search_filter requires one {username}")
        remainder = self.user_search_filter.replace("{username}", "")
        if "{" in remainder or "}" in remainder:
            raise ValueError("security.ldap.user_search_filter contains unknown placeholders")
        for name in (
            "username_attribute",
            "email_attribute",
            "external_id_attribute",
            "group_member_attribute",
        ):
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", getattr(self, name)):
                raise ValueError(f"security.ldap.{name} must be an LDAP attribute name")
        if (self.group_member_attribute.lower(), self.group_member_value_type) not in {
            ("memberuid", "username"),
            ("member", "dn"),
        }:
            raise ValueError("LDAP direct membership requires memberUid/username or member/dn")
