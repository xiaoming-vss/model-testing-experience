from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.enums import ImportStatus
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrFunctionTestSuiteNameAlreadyUse,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.function_case_content import (
    from_legacy,
    legacy_fields,
    set_legacy_content,
)
from testing_agent.domain.function_case_identity import pinned_case_id
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.services.ai_generate_task import (
    AiGenerateTaskService,
    dump_run,
    generated_function_cases,
    validate_function_candidate_cases,
)


def normalized_case_name(name: Any) -> str:
    return str(name or "").strip().casefold()


def generated_case_comparison(item: dict[str, Any]) -> dict[str, Any]:
    text = legacy_fields(
        from_legacy(item["preconditions"], item["steps"], item["expected_results"])
    )
    return {
        "module": item["module"],
        "title": item["title"],
        "preconditions": text["preconditions"],
        "steps": text["steps"],
        "expectedResults": text["expected_results"],
        "priority": item["priority"],
        "caseType": item["case_type"],
    }


def stored_case_comparison(case: FunctionTestCase) -> dict[str, Any]:
    text = legacy_fields(
        getattr(case, "content_json", None)
        or from_legacy(case.preconditions, case.steps, case.expected_results)
    )
    return {
        "module": case.module,
        "title": case.title,
        "preconditions": text["preconditions"],
        "steps": text["steps"],
        "expectedResults": text["expected_results"],
        "priority": case.priority,
        "caseType": case.case_type,
    }


def apply_generated_case(case: FunctionTestCase, item: dict[str, Any]) -> None:
    case.module = item["module"]
    case.title = item["title"]
    set_legacy_content(case, item["preconditions"], item["steps"], item["expected_results"])
    case.priority = item["priority"]
    case.case_type = item["case_type"]


async def import_function_run(
    service: AiGenerateTaskService,
    run_id: str,
    confirm_overwrite: bool,
    user_id: str,
) -> dict[str, Any]:
    owned_run = await service.owned_run(user_id, run_id, "function")
    run = await service.repository.get_run_for_update(run_id)
    if run is None or run.run_id != owned_run.run_id:
        raise ErrBadRequest
    if (
        run.status != "success"
        or run.review_status != "approved"
        or run.import_status == ImportStatus.IMPORTED.value
    ):
        raise ErrBadRequest
    await service.ensure_requirement_access(user_id, run.requirement_id)

    raw_cases = generated_function_cases(run)
    if not raw_cases:
        raise ErrBadRequest
    generated_cases = validate_function_candidate_cases(raw_cases)

    suites_by_module: dict[str, FunctionTestSuite | None] = {}
    existing_by_module: dict[str, dict[str, FunctionTestCase]] = {}
    conflicts: list[dict[str, Any]] = []

    for item in generated_cases:
        module = item["module"]
        normalized_name = normalized_case_name(item["title"])

        if module not in suites_by_module:
            suite = await service.repository.get_function_suite_by_requirement_and_name(
                run.requirement_id, module
            )
            suites_by_module[module] = suite
            existing_cases = (
                await service.repository.list_function_cases(suite.suite_id)
                if suite is not None
                else []
            )
            existing_by_name: dict[str, FunctionTestCase] = {}
            for existing_case in existing_cases:
                existing_name = normalized_case_name(existing_case.title)
                if existing_name in existing_by_name:
                    raise ErrBadRequest
                existing_by_name[existing_name] = existing_case
            existing_by_module[module] = existing_by_name

        existing = existing_by_module[module].get(normalized_name)
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
        target_ids: list[str] = []
        max_order_by_suite: dict[str, int] = {}
        for module, suite in list(suites_by_module.items()):
            if suite is None:
                suite = FunctionTestSuite(
                    suite_id=new_id(),
                    requirement_id=run.requirement_id,
                    name=module,
                    description="",
                )
                service.repository.add(suite)
                suites_by_module[module] = suite
            target_ids.append(suite.suite_id)

        for item in generated_cases:
            module = item["module"]
            suite = suites_by_module[module]
            if suite is None:
                raise ErrBadRequest
            existing = existing_by_module[module].get(normalized_case_name(item["title"]))
            if existing is not None:
                apply_generated_case(existing, item)
                continue

            max_order = max_order_by_suite.get(suite.suite_id)
            if max_order is None:
                max_order = await service.repository.max_function_case_order_by_suite(
                    suite.suite_id
                )
            max_order += 1
            max_order_by_suite[suite.suite_id] = max_order
            new_case = FunctionTestCase(
                case_id=await pinned_case_id(service.repository, item["case_id"]),
                suite_id=suite.suite_id,
                order_no=max_order,
            )
            apply_generated_case(new_case, item)
            service.repository.add(new_case)

        run.import_status = ImportStatus.IMPORTED.value
        run.imported_targets = [
            {"targetType": "function_suite", "targetId": target_id} for target_id in target_ids
        ]
        run.imported_at = datetime.now(UTC)
        run.import_migration_complete = True
        await service.repository.commit()
        await service.repository.refresh(run)
    except Exception as exc:
        (
            run.import_status,
            run.imported_targets,
            run.imported_at,
            run.import_migration_complete,
        ) = old_import_state
        await service.repository.rollback()
        # Concurrent inserts may collide during autoflush or commit; translate only the
        # suite business key, preserving unrelated database failures.
        if isinstance(exc, IntegrityError) and (
            "uk_function_suite_requirement_name" in str(exc.orig)
            or "UNIQUE constraint failed: function_test_suites.requirement_id, "
            "function_test_suites.name"
            in str(exc.orig)
        ):
            raise dynamic_error(
                ErrFunctionTestSuiteNameAlreadyUse,
                "该需求下的功能测试集名称已被占用，请检查生成结果的模块名称或刷新后重试",
            ) from exc
        raise

    return {
        "requiresConfirmation": False,
        "conflicts": [],
        "run": dump_run(run),
    }
