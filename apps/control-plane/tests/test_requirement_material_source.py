import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from testing_agent.core.errors import AppError
from testing_agent.services.requirement_material_source import (
    approved_material,
    material_source,
    material_version_ref,
)


class Repository:
    def __init__(self, versions):
        self.versions = versions

    async def task(self, requirement_id, kind):
        return SimpleNamespace(task_id="task") if requirement_id == "r" else None

    async def version(self, task_id, version_id):
        return next((v for v in self.versions if v.version_id == version_id), None)

    async def latest_version(self, task_id, stage):
        return next((v for v in reversed(self.versions) if v.stage == stage), None)


def version(version_id="v1", stage="extracting_text", content=None):
    if content is None:
        content = Path(
            "tests/fixtures/requirement_artifacts/readable-material.example.json"
        ).read_text()
    return SimpleNamespace(
        version_id=version_id,
        version_no=1,
        task_id="task",
        attempt_id="attempt",
        stage=stage,
        artifact_content=content,
    )


async def test_material_selection_is_scoped_and_rejects_other_stage():
    old, latest, understanding = (
        version("v1"),
        version("v2"),
        version("v3", "feature_understanding"),
    )
    repo = Repository([old, latest, understanding])
    assert await approved_material(repo, "r") is latest
    assert await approved_material(repo, "r", "v1") is old
    with pytest.raises(AppError):
        await approved_material(repo, "r", "v3")
    with pytest.raises(AppError):
        await approved_material(repo, "foreign", "v1")
    assert await approved_material(repo, "foreign") is None


def test_material_source_validates_and_preserves_full_artifact():
    item = version()
    assert json.loads(material_source(item)) == json.loads(item.artifact_content)
    assert material_version_ref(item)["versionId"] == "v1"
    with pytest.raises(AppError):
        material_source(version(content='{"artifactType":"requirement_understanding"}'))
