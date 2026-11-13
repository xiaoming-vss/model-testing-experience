"""Validation of traceable test points and their frozen sources."""

import json

import pytest

from testing_agent.domain.traceable_test_points import validate_traceable_test_points


def refs() -> dict:
    return {
        "materialBlockIds": ["B1"],
        "testObjectIds": ["T1"],
        "impactAreaIds": [],
        "riskIds": [],
        "materialQuestionIds": [],
        "scopeQuestionIds": [],
    }


def artifact() -> dict:
    return {
        "schemaVersion": "1.0",
        "artifactType": "traceable_test_points",
        "reviewStatus": "independent_reviewed",
        "testPoints": [
            {
                "id": "P1",
                "module": "配置",
                "dimension": "功能场景",
                "name": "【配置】验证保存配置",
                "basis": "direct",
                **refs(),
            }
        ],
        "coverageGaps": [],
    }


def sources() -> tuple[dict, dict]:
    return (
        {"materialBlocks": [{"id": "B1"}], "questions": []},
        {"testObjects": [{"id": "T1"}], "impactAreas": [], "risks": [], "openQuestions": []},
    )


def test_accepts_traceable_point_against_frozen_sources() -> None:
    validate_traceable_test_points(artifact(), *sources())


def test_rejects_unknown_material_reference() -> None:
    value = artifact()
    value["testPoints"][0]["materialBlockIds"] = ["other"]
    with pytest.raises(ValueError, match="materialBlockIds"):
        validate_traceable_test_points(value, *sources())


def test_rejects_invalid_name_and_duplicate_id() -> None:
    value = artifact()
    value["testPoints"][0]["name"] = "【错误】验证保存配置"
    with pytest.raises(ValueError, match="功能项"):
        validate_traceable_test_points(value, *sources())
    value = artifact()
    value["testPoints"].append(dict(value["testPoints"][0]))
    with pytest.raises(ValueError, match="标识重复"):
        validate_traceable_test_points(value, *sources())


async def test_stage_validates_frozen_material_and_analysis() -> None:
    from types import SimpleNamespace

    from testing_agent.core.errors import AppError
    from testing_agent.services.generation_artifact_validation import validate_generation_artifact

    material, scope = sources()
    snapshot = {
        "source": {"sourceContent": json.dumps(material)},
        "config": {"requirementAnalysis": scope},
    }
    result, _ = await validate_generation_artifact(
        SimpleNamespace(), "function", "case_names", json.dumps(artifact()), snapshot
    )
    assert json.loads(result)["testPoints"][0]["id"] == "P1"
    scope["testObjects"] = []
    with pytest.raises(AppError):
        await validate_generation_artifact(
            SimpleNamespace(), "function", "case_names", json.dumps(artifact()), snapshot
        )


async def test_worker_event_uses_frozen_analysis_for_reference_validation() -> None:
    from testing_agent.core.errors import AppError
    from testing_agent.services.stage_storage.worker_events import _artifact

    material, scope = sources()
    source = {"sourceContent": json.dumps(material)}
    config = {"caseNames": artifact(), "requirementAnalysis": scope}
    content, _ = await _artifact(None, "function", "case_names", source, config, None)
    assert json.loads(content)["testPoints"][0]["id"] == "P1"
    scope["testObjects"] = []
    with pytest.raises(AppError):
        await _artifact(None, "function", "case_names", source, config, None)
