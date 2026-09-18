from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from testing_agent.core.enums import ImportStatus
from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.services.ai_generate_task import dump_run, validate_ui_candidate_cases

if TYPE_CHECKING:
    from testing_agent.services.ai_generate_task import AiGenerateTaskService


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
    }


def apply_generated_case(case: UiTestCase, item: dict[str, Any]) -> None:
    case.name = item["name"]
    case.enabled = item["enabled"]
    case.order_no = item["orderNo"]
    case.steps_json = item["stepsJson"]


async def import_ui_run(
    service: AiGenerateTaskService,
    run_id: str,
    suite_id: str,
    confirm_overwrite: bool,
    user_id: str,
) -> dict[str, Any]:
    owned_run = await service.owned_run(user_id, run_id, "ui", action="execute")
    run = await service.repository.get_run_for_update(run_id)
    if run is None or run.run_id != owned_run.run_id:
        raise ErrBadRequest
    if (
        run.status != "success"
        or run.review_status != "approved"
        or run.import_status == ImportStatus.IMPORTED.value
    ):
        raise ErrBadRequest

    suite = await service.repository.get_ui_suite(suite_id)
    if suite is None:
        raise ErrNotFound
    await service.ensure_requirement_access(user_id, suite.requirement_id, action="execute")

    generated_cases = validate_ui_candidate_cases(run.result_yaml)
    generated_names: set[str] = set()
    for item in generated_cases:
        normalized_name = normalized_case_name(item["name"])
        if normalized_name in generated_names:
            raise ErrBadRequest
        generated_names.add(normalized_name)

    existing_cases = await service.repository.list_ui_cases(suite_id)
    existing_by_name: dict[str, UiTestCase] = {}
    for case in existing_cases:
        normalized_name = normalized_case_name(case.name)
        if normalized_name in existing_by_name:
            raise ErrBadRequest
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

    if conflicts and not confirm_overwrite:
        return {
            "requiresConfirmation": True,
            "conflicts": conflicts,
            "run": dump_run(run),
        }

    old_import_state = (
        run.import_status,
        run.imported_targets,
        run.imported_at,
        run.import_migration_complete,
    )
    try:
        for item in generated_cases:
            target = existing_by_name.get(normalized_case_name(item["name"]))
            if target is None:
                target = UiTestCase(case_id=new_id(), suite_id=suite_id)
                service.repository.add(target)
            apply_generated_case(target, item)

        run.import_status = ImportStatus.IMPORTED.value
        run.imported_targets = [{"targetType": "ui_suite", "targetId": suite_id}]
        run.imported_at = datetime.now(UTC)
        run.import_migration_complete = True
        await service.repository.commit()
        await service.repository.refresh(run)
    except Exception:
        (
            run.import_status,
            run.imported_targets,
            run.imported_at,
            run.import_migration_complete,
        ) = old_import_state
        await service.repository.rollback()
        raise

    return {
        "requiresConfirmation": False,
        "conflicts": [],
        "run": dump_run(run),
    }
