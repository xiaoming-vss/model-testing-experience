"""Directory results independent of LDAP transport and platform persistence."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DirectoryIdentity:
    external_id: str
    username: str
    dn: str
    emails: tuple[str, ...]
    enabled: bool
    direct_member: bool

    @property
    def eligible(self) -> bool:
        return self.enabled and self.direct_member


class DirectoryUnavailable(Exception):
    """Incomplete or untrusted directory result; never mutate local account state."""


class DirectoryCredentialsRejected(Exception):
    """User credentials rejected; may contribute to login failure accounting."""
