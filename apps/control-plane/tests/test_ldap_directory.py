from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from testing_agent.core.ldap_config import LdapSettings
from testing_agent.core.ldap_directory import LdapDirectory
from testing_agent.domain.ldap_identity import DirectoryCredentialsRejected, DirectoryUnavailable

IDENTITY = "550e8400-e29b-41d4-a716-446655440000"


def settings(**changes):
    return replace(
        LdapSettings(
            enabled=True,
            server_url="ldap://directory.test",
            bind_dn="uid=reader,dc=test",
            bind_password="test-secret",
            user_search_base="cn=users,dc=test",
            access_group_dn="cn=platform,dc=test",
            directory_rules_verified=True,
            # Synthetic fixture values, NOT Synology mappings.
            active_user_filter="(testState=active)",
            disabled_user_filter="(testState=disabled)",
        ),
        **changes,
    )


def entry(**attributes):
    return {
        "type": "searchResEntry",
        "dn": "uid=alice,cn=users,dc=test",
        "attributes": {
            "entryUUID": [IDENTITY.upper()],
            "uid": ["alice"],
            "mail": ["alice@example.test"],
            **attributes,
        },
    }


def connection():
    conn = MagicMock()
    conn.closed = False
    conn.bind.return_value = True
    conn.start_tls.return_value = True
    conn.result = {"result": 0}
    return conn


def install_directory_search(conn, *, disabled=False, member=True):
    def search(base, query, **kwargs):
        conn.result = {"result": 0}
        if query == "(objectClass=*)":
            conn.response = [entry(objectClass=["posixGroup"])]
        elif query == "(testState=active)":
            conn.response = [] if disabled else [entry()]
        elif query == "(testState=disabled)":
            conn.response = [entry()] if disabled else []
        else:
            conn.response = [entry()]
        return bool(conn.response)

    def compare(*args):
        conn.result = {"result": 6 if member else 5}
        return member

    conn.search.side_effect = search
    conn.compare.side_effect = compare


async def test_lookup_escapes_input_requests_uuid_and_normalizes_identity():
    conn = connection()
    install_directory_search(conn)
    with patch("testing_agent.core.ldap_directory.Connection", return_value=conn):
        identity = await LdapDirectory(settings()).lookup("a*)(uid=*)")
    assert identity.external_id == IDENTITY
    assert identity.eligible
    query = conn.search.call_args_list[2]
    assert query.args[1] == r"(uid=a\2a\29\28uid=\2a\29)"
    assert "entryUUID" in query.kwargs["attributes"]
    conn.unbind.assert_called_once()


async def test_query_and_password_bind_use_separate_connections_and_tls_first():
    service, user = connection(), connection()
    install_directory_search(service)
    with patch(
        "testing_agent.core.ldap_directory.Connection", side_effect=[service, user]
    ) as factory:
        directory = LdapDirectory(settings())
        identity = await directory.lookup("alice")
        await directory.verify_password(identity, "x" * 100)
    assert factory.call_args_list[0].kwargs["user"] == settings().bind_dn
    assert factory.call_args_list[1].kwargs["user"] == identity.dn
    assert factory.call_args_list[1].kwargs["password"] == "x" * 100
    assert [call[0] for call in user.method_calls][:3] == ["open", "start_tls", "bind"]
    assert not factory.call_args.kwargs["auto_referrals"]
    assert factory.call_args.kwargs["read_only"]
    service.unbind.assert_called_once()
    user.unbind.assert_called_once()


async def test_tls_failure_never_sends_password_and_closes():
    conn = connection()
    conn.start_tls.return_value = False
    with patch("testing_agent.core.ldap_directory.Connection", return_value=conn):
        with pytest.raises(DirectoryUnavailable):
            await LdapDirectory(settings()).lookup("alice")
    conn.bind.assert_not_called()
    conn.unbind.assert_called_once()


@pytest.mark.parametrize(
    "user,code,exception",
    [
        (True, 49, DirectoryCredentialsRejected),
        (False, 49, DirectoryUnavailable),
        (True, 52, DirectoryUnavailable),
    ],
)
def test_bind_failure_classification(user, code, exception):
    conn = connection()
    conn.bind.return_value = False
    conn.result = {"result": code}
    with patch("testing_agent.core.ldap_directory.Connection", return_value=conn):
        with pytest.raises(exception):
            with LdapDirectory(settings())._connection("test-dn", "password", user=user):
                pytest.fail("must not bind")
    conn.unbind.assert_called_once()


@pytest.mark.parametrize(
    "code,response",
    [
        (4, [entry()]),
        (3, []),
        (50, []),
        (0, [entry(), entry()]),
        (0, [{"type": "searchResRef"}]),
    ],
)
def test_partial_results_referrals_and_ambiguity_are_not_absence(code, response):
    conn = connection()
    conn.result = {"result": code}
    conn.response = response
    with pytest.raises(DirectoryUnavailable):
        LdapDirectory(settings())._search(conn, "dc=test", "(uid=x)", ["uid"])


@pytest.mark.parametrize("attributes", [{"entryUUID": []}, {"entryUUID": ["invalid"]}, {"uid": []}])
def test_missing_identity_never_falls_back_to_username(attributes):
    with pytest.raises(DirectoryUnavailable):
        LdapDirectory(settings())._identity(connection(), entry(**attributes))


async def test_rules_unverified_fail_without_connecting():
    with patch("testing_agent.core.ldap_directory.Connection") as factory:
        with pytest.raises(DirectoryUnavailable, match="unverified"):
            await LdapDirectory(settings(directory_rules_verified=False)).lookup("alice")
    factory.assert_not_called()


async def test_disabled_and_nonmember_are_explicit_ineligible_results():
    conn = connection()
    install_directory_search(conn, disabled=True, member=False)
    with patch("testing_agent.core.ldap_directory.Connection", return_value=conn):
        identity = await LdapDirectory(settings()).lookup("alice")
    assert not identity.enabled and not identity.direct_member and not identity.eligible


async def test_empty_password_never_binds():
    directory = LdapDirectory(settings())
    conn = connection()
    install_directory_search(conn)
    with patch("testing_agent.core.ldap_directory.Connection", return_value=conn) as factory:
        identity = await directory.lookup("alice")
        with pytest.raises(DirectoryCredentialsRejected):
            await directory.verify_password(identity, "")
    assert factory.call_count == 1


async def test_round_failure_does_not_return_partial_results():
    conn = connection()
    install_directory_search(conn)
    directory = LdapDirectory(settings())
    original_search = directory._search

    def fail_second(connection, base, query, attributes, **kwargs):
        if "second-id" in query:
            raise DirectoryUnavailable("incomplete")
        return original_search(connection, base, query, attributes, **kwargs)

    with patch("testing_agent.core.ldap_directory.Connection", return_value=conn):
        with patch.object(directory, "_search", side_effect=fail_second):
            with pytest.raises(DirectoryUnavailable):
                await directory.inspect((IDENTITY, "second-id"))
    conn.unbind.assert_called_once()


def test_dn_membership_delegates_matching_to_server():
    conn = connection()
    install_directory_search(conn)
    directory = LdapDirectory(
        settings(group_member_attribute="member", group_member_value_type="dn")
    )
    identity = directory._identity(conn, entry())
    conn.compare.assert_called_once_with(settings().access_group_dn, "member", identity.dn)
