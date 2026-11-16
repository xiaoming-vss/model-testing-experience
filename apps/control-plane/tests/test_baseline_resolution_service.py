"""Sprint baseline resolution now uses explicit requirement repository associations."""

from __future__ import annotations

from types import SimpleNamespace

from testing_agent.repositories.requirement_software_repository import (
    RequirementRepositoryBinding,
)
from testing_agent.services.baseline_resolution import BaselineResolutionService


def _binding(
    repository_id: str,
    branch: str,
    baseline: str,
    *,
    requirement_id: str = "req-1",
) -> RequirementRepositoryBinding:
    return RequirementRepositoryBinding(
        association=SimpleNamespace(
            requirement_id=requirement_id,
            software_repository_id=repository_id,
            branch=branch,
            baseline_branch=baseline,
        ),
        software_repository=SimpleNamespace(
            software_repository_id=repository_id,
            name=repository_id,
            repository_project_id=repository_id,
        ),
    )


class FakeRepository:
    def __init__(self, bindings: list[RequirementRepositoryBinding]) -> None:
        self.bindings = bindings
        self.calls: list[str] = []

    async def list_for_sprint_with_repository(self, sprint_id: str):
        self.calls.append(sprint_id)
        return self.bindings


async def test_returns_explicit_working_and_baseline_branches():
    repository = FakeRepository([_binding("repo-1", "feature/order", "main")])

    results = await BaselineResolutionService(repository).resolve_for_sprint("sprint-1")

    assert repository.calls == ["sprint-1"]
    assert len(results) == 1
    resolution = results[0].resolution
    assert resolution.repository_id == "repo-1"
    assert resolution.branch == "feature/order"
    assert resolution.baseline_ref == "main"
    assert resolution.error == ""
    assert resolution.note == ""
    assert resolution.dump() == {
        "repositoryId": "repo-1",
        "branch": "feature/order",
        "baselineRef": "main",
        "note": "",
        "error": "",
    }


async def test_each_association_resolves_independently():
    repository = FakeRepository(
        [
            _binding("repo-1", "feature/a", "main"),
            _binding("repo-2", "feature/b", "release-1.0"),
        ]
    )

    results = await BaselineResolutionService(repository).resolve_for_sprint("sprint-1")

    assert [item.resolution.repository_id for item in results] == ["repo-1", "repo-2"]
    assert [item.resolution.branch for item in results] == ["feature/a", "feature/b"]
    assert [item.resolution.baseline_ref for item in results] == ["main", "release-1.0"]


async def test_missing_branches_are_reported_per_repository():
    repository = FakeRepository(
        [
            _binding("repo-1", "", "main"),
            _binding("repo-2", "feature/b", ""),
            _binding("repo-3", "", ""),
        ]
    )

    results = await BaselineResolutionService(repository).resolve_for_sprint("sprint-1")

    assert [item.resolution.error for item in results] == [
        "缺少工作分支或基线分支",
        "缺少工作分支或基线分支",
        "缺少工作分支或基线分支",
    ]
    assert [item.resolution.baseline_ref for item in results] == [
        "main",
        None,
        None,
    ]


async def test_no_associations_returns_empty_list():
    repository = FakeRepository([])

    results = await BaselineResolutionService(repository).resolve_for_sprint("sprint-1")

    assert results == []
