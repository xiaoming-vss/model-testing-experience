from __future__ import annotations

from support.openapi_schema import openapi_schema


def test_openapi_run_contract_omits_legacy_imported_collection_id():
    schema = openapi_schema()["components"]["schemas"]["AiGenerateTaskRunResponse"]

    assert "importedCollectionId" not in schema["properties"]
    assert "importMigrationComplete" not in schema["properties"]
