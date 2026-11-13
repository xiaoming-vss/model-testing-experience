"""Shared naming rules for user-defined environment variables."""

from __future__ import annotations

MAX_LENGTH = 120
RESERVED_NAMES = frozenset({"baseUrl"})
RESERVED_PREFIXES = ("$", "data.")
FORBIDDEN_CHARACTERS = frozenset("{}|")


def validate_variable_name(name: str) -> str:
    """Return the trimmed name or raise ValueError for an unusable variable key."""
    value = (name or "").strip()
    if not value:
        raise ValueError("变量名不能为空")
    if len(value) > MAX_LENGTH:
        raise ValueError(f"变量名不能超过 {MAX_LENGTH} 个字符")
    if FORBIDDEN_CHARACTERS.intersection(value):
        raise ValueError("变量名不能包含 { } 或 |")
    if any(character.isspace() for character in value):
        raise ValueError("变量名不能包含空白字符")
    if value.startswith(RESERVED_PREFIXES):
        raise ValueError("变量名不能以 $ 或 data. 开头")
    if value in RESERVED_NAMES:
        raise ValueError(f"{value} 是内置变量名，不能用作环境变量")
    return value
