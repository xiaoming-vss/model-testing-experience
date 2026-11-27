from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from testing_agent.core.errors import ErrNotFound
from testing_agent.services.project_access import require_project_id


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


async def batch_set_invalidated(
    repository: Any,
    session: Any,
    user_id: str,
    project_id: str,
    case_ids: Sequence[str],
    invalidated: bool,
) -> dict:
    """Apply one project-scoped invalidation command for every case family."""
    await require_project_id(session, user_id, project_id, action="write")
    rows = await repository.list_project_cases_by_ids(project_id, list(case_ids))
    if len(rows) != len(case_ids) or {case.case_id for case in rows} != set(case_ids):
        raise ErrNotFound()
    changed = set_case_invalidated(rows, invalidated)
    try:
        await repository.commit()
    except Exception:
        await repository.rollback()
        raise
    return {"caseIds": list(case_ids), "updatedCount": changed}
