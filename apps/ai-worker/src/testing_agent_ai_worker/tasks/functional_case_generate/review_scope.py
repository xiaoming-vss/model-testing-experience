"""Select revision review targets from changes and unresolved findings."""

from typing import Any

REFERENCE_FIELDS = (
    "materialBlockIds",
    "testObjectIds",
    "impactAreaIds",
    "riskIds",
    "materialQuestionIds",
    "scopeQuestionIds",
)


def revision_scope(
    previous: dict[str, Any], candidate: dict[str, Any], issues: list[dict[str, Any]]
) -> dict[str, Any]:
    """Include direct changes, unresolved targets, and their immediate neighbours.

    Old references and modules matter when a correction moves or deletes a point.
    Reference keys stay namespaced because different collections may reuse an ID.
    """
    changes: dict[str, Any] = {}
    seeds = list(issues)
    changed_point_ids: set[str] = set()
    direct_ids: dict[str, set[str]] = {}
    for group in ("testPoints", "coverageGaps"):
        before = {row["id"]: row for row in previous[group]}
        after = {row["id"]: row for row in candidate[group]}
        changed = [key for key, row in after.items() if row != before.get(key)]
        removed = [key for key in before if key not in after]
        changes[group] = {
            "before": [before[key] for key in [*changed, *removed] if key in before],
            "after": [after[key] for key in changed],
        }
        seeds.extend(changes[group]["before"])
        seeds.extend(changes[group]["after"])
        target_type = "testPoint" if group == "testPoints" else "coverageGap"
        targets = {issue["targetId"] for issue in issues if issue["targetType"] == target_type}
        direct_ids[group] = set(changed) | targets
        seeds.extend(row for key, row in before.items() if key in targets)
        seeds.extend(row for key, row in after.items() if key in targets)
        if group == "testPoints":
            changed_point_ids.update(changed)
            changed_point_ids.update(targets)

    refs = {(field, value) for row in seeds for field in REFERENCE_FIELDS for value in row[field]}
    modules = {row["module"] for row in seeds if "module" in row}

    def affected(row: dict[str, Any]) -> bool:
        return row.get("module") in modules or any(
            (field, value) in refs for field in REFERENCE_FIELDS for value in row[field]
        )

    return {
        "changed": any(part["before"] or part["after"] for part in changes.values()),
        "changes": changes,
        "basis": [row for row in candidate["testPoints"] if row["id"] in changed_point_ids],
        "testPoints": [
            row
            for row in candidate["testPoints"]
            if row["id"] in direct_ids["testPoints"] or affected(row)
        ],
        "coverageGaps": [
            row
            for row in candidate["coverageGaps"]
            if row["id"] in direct_ids["coverageGaps"] or affected(row)
        ],
    }
