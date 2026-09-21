from __future__ import annotations

import builtins
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from testing_agent.core.enums import ImportStatus, ReviewStatus, RunStatus
from testing_agent.core.errors import (
    ErrBadRequest,
)
from testing_agent.core.sid import new_id
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_task_access import OwnedRun, RequireCollectionAccess
from testing_agent.services.ai_task_output import dump_run, generated_payload
from testing_agent.services.api_import_entities import (
    add_api_rules,
    apply_api_case,
    normalize_api_case,
)
from testing_agent.services.api_import_payload import (
    validate_api_collection_import_payload,
)


class ApiCandidateImporter:
    def __init__(
        self,
        *,
        repository: AiGenerateTaskRepository,
        owned_run: OwnedRun,
        ensure_collection_access: RequireCollectionAccess,
        id_factory: Callable[[], str] = new_id,
    ):
        self.repository = repository
        self.owned_run = owned_run
        self.ensure_collection_access = ensure_collection_access
        self.new_id = id_factory

    @staticmethod
    def _normalized_api_case_name(name: Any) -> str:
        return str(name or "").strip().casefold()

    async def _stored_api_case(self, case: ApiCase) -> dict[str, Any]:
        extract_rules = await self.repository.list_api_extract_rules(case.case_id)
        assert_rules = await self.repository.list_api_assert_rules(case.case_id)
        return {
            "name": case.name,
            "description": case.description,
            "enabled": case.enabled,
            "orderNo": case.order_no,
            "method": case.method,
            "urlTemplate": case.url_template,
            "headers": case.headers_json or {},
            "query": case.query_json or {},
            "bodyType": case.body_type,
            "bodyJson": case.body_json,
            "bodyText": case.body_text,
            "timeoutMs": case.timeout_ms,
            "continueOnFailure": case.continue_on_failure,
            "extractRules": [
                {
                    "name": rule.name,
                    "enabled": rule.enabled,
                    "orderNo": rule.order_no,
                    "source": rule.source,
                    "sourceExpr": rule.source_expr,
                    "varKey": rule.var_key,
                    "defaultValue": rule.default_value,
                }
                for rule in extract_rules
            ],
            "assertRules": [
                {
                    "name": rule.name,
                    "enabled": rule.enabled,
                    "orderNo": rule.order_no,
                    "assertSource": rule.assert_source,
                    "targetExpr": rule.target_expr,
                    "comparator": rule.comparator,
                    "expectedValue": rule.expected_value,
                }
                for rule in assert_rules
            ],
        }

    async def _replace_api_rules(self, case_id: str, item: dict[str, Any]) -> None:
        existing_extract = {
            rule.var_key: rule for rule in await self.repository.list_api_extract_rules(case_id)
        }
        existing_assert = {
            rule.name: rule for rule in await self.repository.list_api_assert_rules(case_id)
        }
        generated_extract = {rule["varKey"]: rule for rule in item["extractRules"]}
        generated_assert = {rule["name"]: rule for rule in item["assertRules"]}
        for extract_key, extract_rule in list(existing_extract.items()):
            if extract_key not in generated_extract:
                await self.repository.delete(extract_rule)
        for assert_key, assert_rule in list(existing_assert.items()):
            if assert_key not in generated_assert:
                await self.repository.delete(assert_rule)
        await self.repository.flush()
        for key, values in generated_extract.items():
            matched_extract = existing_extract.get(key)
            if matched_extract is None:
                self.repository.add(
                    ApiExtractRule(
                        extract_rule_id=self.new_id(),
                        case_id=case_id,
                        name=values["name"],
                        enabled=values["enabled"],
                        order_no=values["orderNo"],
                        source=values["source"],
                        source_expr=values["sourceExpr"],
                        var_key=key,
                        default_value=values["defaultValue"],
                    )
                )
            else:
                matched_extract.name = values["name"]
                matched_extract.enabled = values["enabled"]
                matched_extract.order_no = values["orderNo"]
                matched_extract.source = values["source"]
                matched_extract.source_expr = values["sourceExpr"]
                matched_extract.default_value = values["defaultValue"]
        for key, values in generated_assert.items():
            matched_assert = existing_assert.get(key)
            if matched_assert is None:
                self.repository.add(
                    ApiAssertRule(
                        assert_rule_id=self.new_id(),
                        case_id=case_id,
                        name=key,
                        enabled=values["enabled"],
                        order_no=values["orderNo"],
                        assert_source=values["assertSource"],
                        target_expr=values["targetExpr"],
                        comparator=values["comparator"],
                        expected_value=values["expectedValue"],
                    )
                )
            else:
                matched_assert.enabled = values["enabled"]
                matched_assert.order_no = values["orderNo"]
                matched_assert.assert_source = values["assertSource"]
                matched_assert.target_expr = values["targetExpr"]
                matched_assert.comparator = values["comparator"]
                matched_assert.expected_value = values["expectedValue"]

    async def import_api_run(
        self,
        run_id: str,
        collection_id: str,
        confirm_overwrite: bool,
        user_id: str,
    ) -> dict[str, Any]:
        run = await self.owned_run(user_id, run_id, "api", action="execute")
        if (
            run.status != RunStatus.SUCCESS.value
            or run.review_status != ReviewStatus.APPROVED.value
            or run.import_status == ImportStatus.IMPORTED.value
        ):
            raise ErrBadRequest
        await self.ensure_collection_access(user_id, collection_id, action="execute")
        raw_cases = await validate_api_collection_import_payload(
            self.repository,
            collection_id,
            generated_payload(run),
            check_existing=False,
        )
        generated_cases = [normalize_api_case(item, index) for index, item in enumerate(raw_cases)]
        existing_cases = await self.repository.list_api_cases(collection_id)
        existing_by_name: dict[str, ApiCase] = {}
        for case in existing_cases:
            normalized_name = self._normalized_api_case_name(case.name)
            if normalized_name in existing_by_name:
                raise ErrBadRequest
            existing_by_name[normalized_name] = case
        conflicts: builtins.list[dict[str, Any]] = []
        for item in generated_cases:
            normalized_name = self._normalized_api_case_name(item["name"])
            existing = existing_by_name.get(normalized_name)
            if existing is not None:
                conflicts.append(
                    {
                        "normalizedName": normalized_name,
                        "existingCase": await self._stored_api_case(existing),
                        "generatedCase": item,
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
                normalized_name = self._normalized_api_case_name(item["name"])
                target_case = existing_by_name.get(normalized_name)
                if target_case is None:
                    target_case = ApiCase(case_id=self.new_id(), collection_id=collection_id)
                    apply_api_case(target_case, item)
                    self.repository.add(target_case)
                    add_api_rules(self.repository, target_case.case_id, item)
                else:
                    apply_api_case(target_case, item)
                    await self._replace_api_rules(target_case.case_id, item)
            imported_at = datetime.now(UTC)
            run.import_status = ImportStatus.IMPORTED.value
            run.imported_targets = [{"targetType": "api_collection", "targetId": collection_id}]
            run.imported_at = imported_at
            run.import_migration_complete = True
            await self.repository.commit()
            await self.repository.refresh(run)
        except Exception:
            (
                run.import_status,
                run.imported_targets,
                run.imported_at,
                run.import_migration_complete,
            ) = old_import_state
            await self.repository.rollback()
            raise
        return {
            "requiresConfirmation": False,
            "conflicts": [],
            "run": dump_run(run),
        }
