from __future__ import annotations

from typing import TYPE_CHECKING, Any

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.services.ai_task_output import validate_ui_candidate_cases
from testing_agent.services.import_payload import parse_import_payload
from testing_agent.services.standalone_run import StandaloneRun
from testing_agent.services.ui_generation_contracts import is_ui_workflow
from testing_agent.services.ui_test_case import validate_ui_import_payload

if TYPE_CHECKING:
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
    }


def apply_generated_case(case: UiTestCase, item: dict[str, Any]) -> None:
    case.name = item["name"]
    case.enabled = item["enabled"]
    case.order_no = item["orderNo"]
    case.steps_json = item["stepsJson"]


async def import_ui_run(
    service: CandidateImportContext,
    run_id: str,
    suite_id: str,
    confirm_overwrite: bool,
    user_id: str,
    *,
    artifact_content: str | None = None,
    allow_reimport: bool = False,
    approved_source: Any | None = None,
) -> dict[str, Any]:
    if approved_source is None:
        owned_run = await service.owned_run(user_id, run_id, "ui", action="execute")
        if not isinstance(owned_run, StandaloneRun):
            raise ErrNotFound()
        from testing_agent.services.standalone_ui_import import import_standalone_ui

        return await import_standalone_ui(
            service,
            owned_run,
            suite_id=suite_id,
            confirm_overwrite=confirm_overwrite,
            user_id=user_id,
            apply_import=import_ui_run,
        )
    run = approved_source
    if artifact_content is None and (
        run.status != "success"
        or run.review_status != "approved"
        or (run.import_status == "imported" and not allow_reimport)
    ):
        raise ErrBadRequest()

    suite = await service.repository.get_ui_suite(suite_id)
    if suite is None:
        raise ErrNotFound()
    await service.ensure_requirement_access(user_id, suite.requirement_id, action="execute")

    raw_content = (run.result_yaml or "") if artifact_content is None else artifact_content
    generated_cases = (
        validate_ui_import_payload(parse_import_payload(raw_content))
        if is_ui_workflow(run)
        else validate_ui_candidate_cases(raw_content)
    )
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

    if conflicts and not confirm_overwrite:
        return {
            "requiresConfirmation": True,
            "conflicts": conflicts,
            "importChanges": [],
            "run": {},
        }

    try:
        changed_case_ids: set[str] = set()
        for item in generated_cases:
            target = existing_by_name.get(normalized_case_name(item["name"]))
            if target is None:
                target = UiTestCase(case_id=new_id(), suite_id=suite_id)
                service.repository.add(target)
            apply_generated_case(target, item)
            changed_case_ids.add(target.case_id)

        await service.repository.flush()
    except Exception:
        await service.repository.rollback()
        raise

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
        "run": {},
    }
