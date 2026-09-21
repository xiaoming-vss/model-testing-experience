from __future__ import annotations

from typing import Any

from testing_agent.core.errors import (
    ErrApiCollectionImportFileRequired,
    ErrNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.repositories.api_collection import ApiCollectionRepository
from testing_agent.schemas.api_collection import ApiCollectionRequest, ApiCollectionResponse
from testing_agent.services.api_import_entities import (
    add_api_rules,
    apply_api_case,
    normalize_api_case,
)
from testing_agent.services.api_import_payload import (
    ALLOWED_IMPORT_ASSERT_SOURCES as ALLOWED_IMPORT_ASSERT_SOURCES,
)
from testing_agent.services.api_import_payload import (
    ALLOWED_IMPORT_BODY_TYPES as ALLOWED_IMPORT_BODY_TYPES,
)
from testing_agent.services.api_import_payload import (
    ALLOWED_IMPORT_COMPARATORS as ALLOWED_IMPORT_COMPARATORS,
)
from testing_agent.services.api_import_payload import (
    ALLOWED_IMPORT_EXTRACT_SOURCES as ALLOWED_IMPORT_EXTRACT_SOURCES,
)
from testing_agent.services.api_import_payload import (
    ALLOWED_IMPORT_METHODS as ALLOWED_IMPORT_METHODS,
)
from testing_agent.services.api_import_payload import (
    IMPORT_ASSERT_RULE_FIELDS as IMPORT_ASSERT_RULE_FIELDS,
)
from testing_agent.services.api_import_payload import (
    IMPORT_CASE_FIELDS as IMPORT_CASE_FIELDS,
)
from testing_agent.services.api_import_payload import (
    IMPORT_EXTRACT_RULE_FIELDS as IMPORT_EXTRACT_RULE_FIELDS,
)
from testing_agent.services.api_import_payload import (
    bool_value as bool_value,
)
from testing_agent.services.api_import_payload import (
    check_unknown_fields as check_unknown_fields,
)
from testing_agent.services.api_import_payload import (
    import_error as import_error,
)
from testing_agent.services.api_import_payload import (
    import_items as import_items,
)
from testing_agent.services.api_import_payload import (
    int_value as int_value,
)
from testing_agent.services.api_import_payload import (
    normalize_import_body_type as normalize_import_body_type,
)
from testing_agent.services.api_import_payload import (
    normalize_import_method as normalize_import_method,
)
from testing_agent.services.api_import_payload import (
    normalize_json_value as normalize_json_value,
)
from testing_agent.services.api_import_payload import (
    parse_import_payload as parse_import_payload,
)
from testing_agent.services.api_import_payload import (
    read_import_payload as read_import_payload,
)
from testing_agent.services.api_import_payload import (
    repository_case_exists as repository_case_exists,
)
from testing_agent.services.api_import_payload import (
    require_string_map as require_string_map,
)
from testing_agent.services.api_import_payload import (
    validate_api_collection_import_payload as validate_api_collection_import_payload,
)
from testing_agent.services.api_import_payload import (
    validate_import_body as validate_import_body,
)
from testing_agent.services.common import apply_patch, dump, list_payload
from testing_agent.services.project_access import (
    ProjectAction,
    require_requirement_access,
)


class ApiCollectionService:
    def __init__(self, repository: ApiCollectionRepository):
        self.repository = repository

    async def ensure_requirement_access(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> None:
        await require_requirement_access(self.repository, user_id, requirement_id, action=action)

    async def get_accessible_entity(
        self, user_id: str, collection_id: str, *, action: ProjectAction = "read"
    ) -> ApiCollection:
        collection = await self.repository.get_collection(collection_id)
        if collection is None:
            raise ErrNotFound
        await self.ensure_requirement_access(user_id, collection.requirement_id, action=action)
        return collection

    async def create(self, user_id: str, requirement_id: str, body: ApiCollectionRequest) -> dict:
        await self.ensure_requirement_access(user_id, requirement_id, action="write")
        collection = ApiCollection(
            collection_id=new_id(),
            requirement_id=requirement_id,
            name=body.name,
            description=body.description,
        )
        self.repository.add(collection)
        await self.repository.commit()
        await self.repository.refresh(collection)
        return dump(ApiCollectionResponse, collection)

    async def list(self, user_id: str, requirement_id: str) -> dict[str, Any]:
        await self.ensure_requirement_access(user_id, requirement_id, action="read")
        rows = await self.repository.list_by_requirement(requirement_id)
        return list_payload([dump(ApiCollectionResponse, row) for row in rows])

    async def get(self, user_id: str, collection_id: str) -> dict:
        return dump(
            ApiCollectionResponse,
            await self.get_accessible_entity(user_id, collection_id, action="read"),
        )

    async def update(self, user_id: str, collection_id: str, body: dict[str, Any]) -> dict:
        collection = await self.get_accessible_entity(user_id, collection_id, action="write")
        apply_patch(collection, body, {"name", "description"})
        await self.repository.commit()
        await self.repository.refresh(collection)
        return dump(ApiCollectionResponse, collection)

    async def delete(self, user_id: str, collection_id: str) -> dict:
        collection = await self.get_accessible_entity(user_id, collection_id, action="write")
        await self.repository.hard_delete(collection)
        await self.repository.commit()
        return {}

    async def import_cases(self, user_id: str, collection_id: str, payload: Any, file: Any) -> dict:
        collection = await self.get_accessible_entity(user_id, collection_id, action="write")
        if file is not None:
            filename = str(getattr(file, "filename", "") or "")
            if not filename:
                raise ErrApiCollectionImportFileRequired
            if not filename.lower().endswith((".yaml", ".yml")):
                raise import_error("仅支持导入 .yaml 或 .yml 文件")
        parsed = await read_import_payload(payload, file)
        cases = await validate_api_collection_import_payload(
            self.repository, collection.collection_id, parsed
        )
        imported_case_count = 0
        imported_extract_rule_count = 0
        imported_assert_rule_count = 0
        for index, item in enumerate(cases):
            normalized = normalize_api_case(item, index, source="file")
            case = ApiCase(case_id=new_id(), collection_id=collection_id)
            apply_api_case(case, normalized)
            self.repository.add(case)
            add_api_rules(self.repository, case.case_id, normalized)
            imported_extract_rule_count += len(normalized["extractRules"])
            imported_assert_rule_count += len(normalized["assertRules"])
            imported_case_count += 1
        await self.repository.commit()
        return {
            "collectionId": collection.collection_id,
            "importedCaseCount": imported_case_count,
            "importedExtractRuleCount": imported_extract_rule_count,
            "importedAssertRuleCount": imported_assert_rule_count,
        }
