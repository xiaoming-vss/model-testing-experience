import copy

import pytest

from testing_agent.domain.requirement_artifacts import validate_artifact


def test_readable_material_rejects_broken_references_and_legacy_output():
    value = {
        "schemaVersion": "0.2",
        "artifactType": "readable_requirement_material",
        "title": "材料",
        "sources": [{"id": "S", "name": "原文", "type": "document", "location": None}],
        "materialBlocks": [
            {
                "id": "B",
                "sourceId": "S",
                "parentId": None,
                "kind": "paragraph",
                "locator": "第1段",
                "content": {"text": "材料内容"},
            }
        ],
        "functions": [
            {
                "id": "F",
                "name": "功能",
                "sections": [
                    {
                        "title": "功能使用与业务规则",
                        "items": [
                            {"text": "执行操作", "status": "confirmed", "materialBlockIds": ["B"]}
                        ],
                    }
                ],
            }
        ],
        "questions": [],
    }
    assert validate_artifact(value, "document_extraction") == value
    invalid = copy.deepcopy(value)
    invalid["functions"][0]["sections"][0]["items"][0]["materialBlockIds"] = ["missing"]
    with pytest.raises(ValueError):
        validate_artifact(invalid, "document_extraction")
    invalid = copy.deepcopy(value)
    invalid["artifactType"] = "document_extraction"
    invalid["schemaVersion"] = "1.0"
    with pytest.raises(ValueError):
        validate_artifact(invalid, "document_extraction")
