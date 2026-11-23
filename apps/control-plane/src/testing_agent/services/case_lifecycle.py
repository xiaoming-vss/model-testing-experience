from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any


def set_case_invalidated(cases: Sequence[Any], invalidated: bool) -> int:
    """设置或清除用例失效时间；重复设置保持首次失效时间，返回实际改变的行数。"""
    moment = datetime.now(UTC)
    changed = 0
    for case in cases:
        if invalidated:
            if case.invalidated_at is None:
                case.invalidated_at = moment
                changed += 1
        elif case.invalidated_at is not None:
            case.invalidated_at = None
            changed += 1
    return changed
