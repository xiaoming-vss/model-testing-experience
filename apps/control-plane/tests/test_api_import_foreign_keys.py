"""API file import persists cases before their dependent rules."""

from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.repositories.api_collection import ApiCollectionRepository
from testing_agent.services.api_collection import ApiCollectionService


async def test_file_import_with_rules_respects_foreign_keys(db):  # noqa: F811
    seed_task(db)
    db.add(ApiCollection(collection_id="target", requirement_id="r", name="target"))
    db.commit()
    service = ApiCollectionService(ApiCollectionRepository(AsyncSessionAdapter(db)))
    result = await service.import_cases(
        "u",
        "target",
        {
            "cases": [
                {
                    "name": "login",
                    "method": "POST",
                    "urlTemplate": "/login",
                    "extractRules": [
                        {
                            "name": "token",
                            "source": "body_jsonpath",
                            "sourceExpr": "$.token",
                            "varKey": "token",
                        }
                    ],
                    "assertRules": [
                        {
                            "name": "status",
                            "assertSource": "status_code",
                            "comparator": "eq",
                            "expectedValue": "200",
                        }
                    ],
                }
            ]
        },
        None,
    )
    assert result["importedCaseCount"] == 1
    case = db.scalar(select(ApiCase).where(ApiCase.collection_id == "target"))
    assert db.scalar(select(ApiExtractRule).where(ApiExtractRule.case_id == case.case_id))
    assert db.scalar(select(ApiAssertRule).where(ApiAssertRule.case_id == case.case_id))
