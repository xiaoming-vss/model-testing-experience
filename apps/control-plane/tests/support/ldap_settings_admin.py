"""Shared preparation for ldap settings admin tests; no collected cases."""

from dataclasses import asdict, replace

from support.ldap_cutover import ldap_settings, session  # noqa: F401
from testing_agent.core.config import Settings


def bootstrap():
    return replace(Settings.from_mapping({}), integration_key="secure-test-encryption-key-for-ldap")


def config():
    return {
        **asdict(ldap_settings().ldap),
        "directory_rules_verified": True,
        "active_user_filter": "(testState=active)",
        "disabled_user_filter": "(testState=disabled)",
    }
