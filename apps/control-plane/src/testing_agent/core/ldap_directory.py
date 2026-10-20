"""Read-only LDAP transport. All blocking operations run outside the event loop.

Directory state filters are deployment-verified Synology predicates, not AD defaults.
The server applies its own matching rules for DN membership via LDAP Compare.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

from ldap3 import (  # type: ignore[import-untyped]
    BASE,
    NONE,
    SIMPLE,
    SUBTREE,
    Connection,
    Server,
    Tls,
)
from ldap3.utils.conv import escape_filter_chars  # type: ignore[import-untyped]

from testing_agent.core.ldap_config import LdapSettings
from testing_agent.domain.ldap_identity import (
    DirectoryCredentialsRejected,
    DirectoryIdentity,
    DirectoryUnavailable,
)

logger = logging.getLogger(__name__)
P = ParamSpec("P")
T = TypeVar("T")


class LdapDirectory:
    def __init__(self, settings: LdapSettings) -> None:
        self.settings = settings

    def _check_rules(self) -> None:
        if (
            not self.settings.enabled
            or not self.settings.directory_rules_verified
            or not self.settings.active_user_filter
            or not self.settings.disabled_user_filter
        ):
            raise DirectoryUnavailable("directory_rules_unverified")

    async def check_connection(self) -> None:
        """Check query credentials and search/group scope, without changing identities."""
        await self._run(self._check_connection)

    def _check_connection(self) -> None:
        with self._connection(self.settings.bind_dn, self.settings.bind_password) as connection:
            self._verify_scope(connection)

    async def lookup(self, username: str) -> DirectoryIdentity | None:
        self._check_rules()
        return await self._run(self._lookup, username)

    async def verify_password(self, identity: DirectoryIdentity, password: str) -> None:
        if not password:
            raise DirectoryCredentialsRejected()
        await self._run(self._verify_password, identity.dn, password)

    async def inspect(self, external_ids: tuple[str, ...]) -> dict[str, DirectoryIdentity | None]:
        """Return a complete round or raise; callers must apply no partial results."""
        self._check_rules()
        return await self._run(self._inspect, external_ids)

    async def _run(self, operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        try:
            async with asyncio.timeout(self.settings.login_timeout_seconds):
                return await asyncio.to_thread(operation, *args, **kwargs)
        except (DirectoryUnavailable, DirectoryCredentialsRejected):
            raise
        except Exception as exc:
            # Third-party exception messages can contain DNs/passwords/server responses.
            logger.warning(
                "LDAP operation failed",
                extra={
                    "error_type": type(exc).__name__,
                    "safe_stack": "".join(
                        traceback.format_list(traceback.extract_tb(exc.__traceback__))
                    ),
                },
            )
            raise DirectoryUnavailable("directory_operation_failed") from None

    @contextmanager
    def _connection(self, dn: str, password: str, *, user: bool = False) -> Iterator[Any]:
        tls = Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=None if self.settings.tls_ca_pem else self.settings.tls_ca_file or None,
            ca_certs_data=self.settings.tls_ca_pem or None,
        )
        server = Server(
            self.settings.server_url,
            tls=tls,
            get_info=NONE,
            connect_timeout=self.settings.timeout_seconds,
        )
        connection = Connection(
            server,
            user=dn,
            password=password,
            authentication=SIMPLE,
            auto_referrals=False,
            auto_range=False,
            read_only=True,
            check_names=False,
            receive_timeout=self.settings.timeout_seconds,
            raise_exceptions=False,
        )
        try:
            connection.open()
            if connection.closed:
                raise DirectoryUnavailable("connection_failed")
            if self.settings.start_tls and not connection.start_tls():
                raise DirectoryUnavailable("tls_failed")
            if not connection.bind():
                if user and (connection.result or {}).get("result") == 49:
                    raise DirectoryCredentialsRejected()
                raise DirectoryUnavailable("bind_failed")
            yield connection
        finally:
            try:
                connection.unbind()
            except Exception:
                # Closing must not obscure the original safe classification.
                logger.warning("LDAP connection cleanup failed")

    def _search(
        self,
        connection: Any,
        base: str,
        query: str,
        attributes: list[str],
        *,
        scope: str = SUBTREE,
    ) -> list[dict[str, Any]]:
        connection.search(
            base,
            query,
            search_scope=scope,
            attributes=attributes,
            size_limit=2,
            time_limit=self.settings.timeout_seconds,
        )
        result = connection.result or {}
        response = connection.response or []
        if (
            result.get("result") != 0
            or result.get("referrals")
            or any(item.get("type") != "searchResEntry" for item in response)
            or len(response) > 1
        ):
            raise DirectoryUnavailable("search_incomplete_or_ambiguous")
        return response

    def _verify_scope(self, connection: Any) -> None:
        for dn in (self.settings.user_search_base, self.settings.access_group_dn):
            rows = self._search(connection, dn, "(objectClass=*)", ["objectClass"], scope=BASE)
            if len(rows) != 1:
                raise DirectoryUnavailable("scope_missing")
            if dn == self.settings.access_group_dn:
                classes = {v.lower() for v in self._values(rows[0], "objectClass")}
                required = (
                    "posixgroup"
                    if self.settings.group_member_value_type == "username"
                    else "groupofnames"
                )
                if required not in classes:
                    raise DirectoryUnavailable("access_group_type_invalid")

    @staticmethod
    def _values(entry: dict[str, Any], name: str) -> tuple[str, ...]:
        attributes = entry.get("attributes", {})
        value: Any = next((v for k, v in attributes.items() if k.lower() == name.lower()), [])
        if isinstance(value, str):
            return (value,)
        if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) for v in value):
            raise DirectoryUnavailable("attribute_invalid")
        return tuple(value)

    def _identity(self, connection: Any, row: dict[str, Any]) -> DirectoryIdentity:
        ids = self._values(row, self.settings.external_id_attribute)
        names = self._values(row, self.settings.username_attribute)
        dn = row.get("dn")
        if len(ids) != 1 or len(names) != 1 or not names[0] or not isinstance(dn, str) or not dn:
            raise DirectoryUnavailable("identity_missing")
        try:
            external_id = str(UUID(ids[0]))
        except ValueError:
            raise DirectoryUnavailable("identity_invalid") from None
        active = bool(
            self._search(
                connection,
                dn,
                self.settings.active_user_filter,
                ["1.1"],
                scope=BASE,
            )
        )
        disabled = bool(
            self._search(
                connection,
                dn,
                self.settings.disabled_user_filter,
                ["1.1"],
                scope=BASE,
            )
        )
        if active == disabled:
            raise DirectoryUnavailable("directory_state_unknown")
        # Compare delegates DN equality to the directory schema; no lowercased string shortcut.
        member = names[0] if self.settings.group_member_value_type == "username" else dn
        connection.compare(
            self.settings.access_group_dn, self.settings.group_member_attribute, member
        )
        code = (connection.result or {}).get("result")
        if code not in (5, 6):
            raise DirectoryUnavailable("membership_unknown")
        return DirectoryIdentity(
            external_id,
            names[0],
            dn,
            self._values(row, self.settings.email_attribute),
            active,
            code == 6,
        )

    @property
    def _attributes(self) -> list[str]:
        # Operational entryUUID is explicitly requested (not included in '*').
        return [
            self.settings.external_id_attribute,
            self.settings.username_attribute,
            self.settings.email_attribute,
        ]

    def _lookup(self, username: str) -> DirectoryIdentity | None:
        with self._connection(self.settings.bind_dn, self.settings.bind_password) as connection:
            self._verify_scope(connection)
            query = self.settings.user_search_filter.replace(
                "{username}", escape_filter_chars(username)
            )
            rows = self._search(connection, self.settings.user_search_base, query, self._attributes)
            return self._identity(connection, rows[0]) if rows else None

    def _verify_password(self, dn: str, password: str) -> None:
        with self._connection(dn, password, user=True):
            pass

    def _inspect(self, external_ids: tuple[str, ...]) -> dict[str, DirectoryIdentity | None]:
        results: dict[str, DirectoryIdentity | None] = {}
        deadline = time.monotonic() + self.settings.login_timeout_seconds
        with self._connection(self.settings.bind_dn, self.settings.bind_password) as connection:
            self._verify_scope(connection)
            for external_id in external_ids:
                if time.monotonic() >= deadline:
                    raise DirectoryUnavailable("round_timeout")
                query = (
                    f"({self.settings.external_id_attribute}={escape_filter_chars(external_id)})"
                )
                rows = self._search(
                    connection, self.settings.user_search_base, query, self._attributes
                )
                if not rows:
                    results[external_id] = None
                    continue
                identity = self._identity(connection, rows[0])
                if identity.external_id != str(UUID(external_id)):
                    raise DirectoryUnavailable("identity_mismatch")
                # Reapply configured scope restrictions using current directory username.
                login_filter = self.settings.user_search_filter.replace(
                    "{username}",
                    escape_filter_chars(identity.username),
                )
                in_scope = self._search(connection, identity.dn, login_filter, ["1.1"], scope=BASE)
                results[external_id] = identity if in_scope else None
        return results
