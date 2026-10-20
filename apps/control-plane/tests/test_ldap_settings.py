import pytest

from testing_agent.core.config import Settings
from testing_agent.core.ldap_config import LdapSettings


def configured(**changes):
    values = dict(
        enabled=True,
        server_url="ldap://directory.example.test:389",
        bind_dn="uid=reader,dc=test",
        bind_password="test-only-secret",
        user_search_base="cn=users,dc=test",
        access_group_dn="cn=platform,dc=test",
    )
    values.update(changes)
    return LdapSettings(**values)


def test_disabled_configuration_needs_no_connection_parameters():
    assert Settings.from_mapping({}).ldap == LdapSettings()


def test_secret_not_in_configuration_representation():
    assert "test-only-secret" not in repr(configured())


def test_plaintext_requires_explicit_permission():
    with pytest.raises(ValueError, match="explicit"):
        configured(start_tls=False)
    assert configured(start_tls=False, allow_insecure_connection=True).enabled


def test_ldaps_does_not_allow_starttls():
    with pytest.raises(ValueError, match="combined"):
        configured(server_url="ldaps://directory.example.test")
    assert configured(server_url="ldaps://directory.example.test", start_tls=False).enabled


@pytest.mark.parametrize(
    "name", ["bind_dn", "bind_password", "access_group_dn", "user_search_base"]
)
def test_enabled_requires_lookup_and_access_scope(name):
    with pytest.raises(ValueError, match=name):
        configured(**{name: ""})


@pytest.mark.parametrize(
    "url",
    [
        "http://directory.test",
        "ldap://user:password@directory.test",
        "ldap://directory.test/base",
        "ldap://directory.test:0",
        "ldap://directory.test:65536",
        "ldap://directory.test?filter=x",
    ],
)
def test_reject_invalid_server_urls_without_leaking_values(url):
    with pytest.raises(ValueError) as error:
        configured(server_url=url)
    assert url not in str(error.value)


@pytest.mark.parametrize(
    "name,value",
    [
        ("enabled", "true"),
        ("timeout_seconds", 0),
        ("token_expire_hours", True),
        ("reconcile_interval_seconds", -1),
        ("user_search_filter", "(uid=*)"),
        ("user_search_filter", "(uid={other})"),
        ("username_attribute", "uid)(x=*"),
        ("group_member_value_type", "dn"),
        ("group_member_attribute", "memberOf"),
    ],
)
def test_reject_invalid_policies(name, value):
    with pytest.raises(ValueError):
        configured(**{name: value})


def test_dn_membership_is_explicit():
    assert configured(group_member_attribute="member", group_member_value_type="dn").enabled


def test_settings_mapping_ignores_legacy_ldap():
    settings = Settings.from_mapping({"security": {"ldap": {"token_expire_hours": 10}}})
    assert settings.ldap == LdapSettings()
