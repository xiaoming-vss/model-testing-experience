"""Platform-issued case identifiers.

Describing cases is the model's job; identity is not. IDs are issued here as UUIDs, so a
case can be referenced from anywhere without colliding with another case from another run.

A revision returns a case set that is a transformation of the previous one. Identity has to
survive that transformation: an edited case keeps its ID, a deleted case takes its ID with
it. The transformation is not reported by the model, so cases are re-matched here, in the
order 「same module and title」 → 「same module and content」 → 「same module, same relative
order」. The last step is a convention, not a proof: a revision that deletes one case and
rewrites both the title and the content of another one is indistinguishable from creating a
case and deleting a different one.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import uuid4


def _text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _identity_of(case: dict[str, Any]) -> str:
    return str(case.get("case_id") or "").strip()


def case_module_of(case: dict[str, Any]) -> str:
    return _text(case.get("case_module") or case.get("module"))


def case_title_of(case: dict[str, Any]) -> str:
    return _text(case.get("case_title") or case.get("title") or case.get("name"))


def case_content_of(case: dict[str, Any]) -> str:
    """Signature of what the case verifies, ignoring how it is titled."""

    steps = _lines(case.get("test_steps") or case.get("steps"))
    expected = _lines(case.get("expected_results") or case.get("expectedResults"))
    return _text(" ".join([*steps, *expected]))


def _take(previous, consumed, module, wanted, attribute) -> str | None:
    """Consume the earliest unconsumed previous case of ``module`` matching ``wanted``."""

    if not wanted:
        return None
    for index, case in enumerate(previous):
        if consumed[index] or case_module_of(case) != module:
            continue
        if attribute(case) == wanted:
            consumed[index] = True
            return _identity_of(case)
    return None


def _inherit(previous: list[dict[str, Any]], cases: list[Any]) -> list[str | None]:
    consumed = [False] * len(previous)
    inherited: list[str | None] = [None] * len(cases)
    leftovers: dict[str, list[int]] = {}

    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            continue
        module = case_module_of(case)
        identifier = _take(previous, consumed, module, case_title_of(case), case_title_of)
        if identifier is None:
            identifier = _take(previous, consumed, module, case_content_of(case), case_content_of)
        if identifier is None:
            leftovers.setdefault(module, []).append(index)
        else:
            inherited[index] = identifier

    for module, indexes in leftovers.items():
        pool = [
            index
            for index, case in enumerate(previous)
            if not consumed[index] and case_module_of(case) == module
        ]
        for position, index in enumerate(indexes):
            if position >= len(pool):
                break
            consumed[pool[position]] = True
            inherited[index] = _identity_of(previous[pool[position]])
    return inherited


def assign_case_ids(cases: list[Any], previous_cases: Iterable[Any] = ()) -> list[Any]:
    """Return ``cases`` with a ``case_id`` first, carrying identity over from ``previous_cases``."""

    previous = [case for case in previous_cases if isinstance(case, dict) and _identity_of(case)]
    inherited = _inherit(previous, cases)

    issued: set[str] = set()
    assigned: list[Any] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            assigned.append(case)
            continue
        identifier = inherited[index]
        if identifier is None or identifier in issued:
            identifier = str(uuid4())
        issued.add(identifier)
        assigned.append(
            {
                "case_id": identifier,
                **{key: value for key, value in case.items() if key != "case_id"},
            }
        )
    return assigned
