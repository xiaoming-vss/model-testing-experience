"""Identity of stored functional cases.

Every functional case carries a platform-issued identifier that is fixed the moment the case
is stored and only disappears together with the case. Cases created by hand or imported from
a file get a fresh identifier; cases imported from an AI candidate set adopt the identifier
that generation minted for them. An adopted identifier that is missing, too long for the
column, or already taken by another stored case is replaced.
"""

from __future__ import annotations

from typing import Any

from testing_agent.core.sid import new_id

CASE_ID_LENGTH = 64


async def pinned_case_id(repository: Any, candidate: Any) -> str:
    """Return the candidate ID when it can become a stored case ID, otherwise a fresh one."""

    value = str(candidate or "").strip()
    if value and len(value) <= CASE_ID_LENGTH and await repository.get_case(value) is None:
        return value
    return new_id()
