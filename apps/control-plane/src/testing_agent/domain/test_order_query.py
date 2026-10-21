"""Bounded entry windows; identity focus and resume keep deep links navigable."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EntryQuery:
    page: int = 1
    page_size: int = 20
    keyword: str = ""
    status: str = ""
    only_mine: bool = False
    focus_entry_id: str = ""
    resume: bool = False
    after_entry_id: str = ""
