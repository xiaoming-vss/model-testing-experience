from __future__ import annotations

from typing import TYPE_CHECKING, Any

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.services.import_payload import parse_import_payload
from testing_agent.services.ui_test_case import validate_ui_import_payload

if TYPE_CHECKING:
    from testing_agent.domain.generation_import_source import CurrentImportSource
    from testing_agent.services.ai_task_access import CandidateImportContext


def normalized_case_name(name: Any) -> str:
    return str(name or "").strip().casefold()


def generated_case_comparison(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "enabled": item["enabled"],
        "orderNo": item["orderNo"],
        "stepsJson": item["stepsJson"],
    }


def stored_case_comparison(case: UiTestCase) -> dict[str, Any]:
    return {
        "name": case.name,
        "enabled": case.enabled,
        "orderNo": case.order_no,
        "stepsJson": case.steps_json,
        "invalidatedAt": case.invalidated_at,
    }


def apply_generated_case(case: UiTestCase, item: dict[str, Any]) -> None:
    case.name = item["name"]
    case.enabled = item["enabled"]
    case.order_no = item["orderNo"]
    case.steps_json = item["stepsJson"]
    case.invalidated_at = None


async def import_ui_run(
    service: CandidateImportContext,
    source: CurrentImportSource,
    suite_id: str,
    confirm_overwrite: bool,
    user_id: str,
    *,
    preview_only: bool = False,
) -> dict[str, Any]:
    suite = await service.repository.get_ui_suite(suite_id)
    if suite is None:
        raise ErrNotFound()
    if suite.requirement_id != source.requirement_id:
        raise ErrBadRequest()
    await service.ensure_requirement_access(user_id, source.requirement_id, action="execute")

    generated_cases = validate_ui_import_payload(parse_import_payload(source.content))
    generated_names: set[str] = set()
    for item in generated_cases:
        normalized_name = normalized_case_name(item["name"])
        if normalized_name in generated_names:
            raise ErrBadRequest()
        generated_names.add(normalized_name)

    existing_cases = await service.repository.list_ui_cases(suite_id)
    existing_by_name: dict[str, UiTestCase] = {}
    for case in existing_cases:
        normalized_name = normalized_case_name(case.name)
        if normalized_name in existing_by_name:
            raise ErrBadRequest()
        existing_by_name[normalized_name] = case

    conflicts = []
    for item in generated_cases:
        normalized_name = normalized_case_name(item["name"])
        existing = existing_by_name.get(normalized_name)
        if existing is not None:
            conflicts.append(
                {
                    "normalizedName": normalized_name,
                    "existingCase": stored_case_comparison(existing),
                    "generatedCase": generated_case_comparison(item),
                }
            )

    if preview_only or (conflicts and not confirm_overwrite):
        return {
            "requiresConfirmation": bool(conflicts),
            "conflicts": conflicts,
            "importChanges": [],
        }

    changed_case_ids: set[str] = set()
    for item in generated_cases:
        target = existing_by_name.get(normalized_case_name(item["name"]))
        if target is None:
            target = UiTestCase(case_id=new_id(), suite_id=suite_id)
            service.repository.add(target)
        apply_generated_case(target, item)
        changed_case_ids.add(target.case_id)

    await service.repository.flush()

    return {
        "requiresConfirmation": False,
        "conflicts": [],
        "importChanges": [
            {
                "targetType": "ui_suite",
                "targetId": suite_id,
                "changedCaseIds": sorted(changed_case_ids),
            }
        ],
    }
