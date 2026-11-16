"""Resolve per-sprint software repository baselines.

Every requirement-software repository association now stores its own working
branch and baseline branch. Sprint overview uses those explicit values and no
longer infers a baseline from previous sprints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from testing_agent.repositories.requirement_software_repository import (
    RequirementRepositoryBinding,
    RequirementSoftwareRepositoryRepository,
)


@dataclass(frozen=True, slots=True)
class RepoBaselineResolution:
    """Single software repository baseline resolution."""

    repository_id: str
    branch: str
    baseline_ref: str | None = None
    note: str = ""
    error: str = ""

    def dump(self) -> dict[str, object]:
        return {
            "repositoryId": self.repository_id,
            "branch": self.branch,
            "baselineRef": self.baseline_ref,
            "note": self.note,
            "error": self.error,
        }


class BindingResolution(NamedTuple):
    """A requirement-software repository association and its baseline."""

    binding: RequirementRepositoryBinding
    resolution: RepoBaselineResolution


class BaselineResolutionService:
    def __init__(self, repository: RequirementSoftwareRepositoryRepository):
        self.repository = repository

    async def resolve_for_sprint(self, sprint_id: str) -> list[BindingResolution]:
        bindings = await self.repository.list_for_sprint_with_repository(sprint_id)
        results: list[BindingResolution] = []
        for binding in bindings:
            repository = binding.software_repository
            branch = binding.association.branch.strip()
            baseline = binding.association.baseline_branch.strip()
            error = ""
            if not branch or not baseline:
                error = "缺少工作分支或基线分支"
            results.append(
                BindingResolution(
                    binding=binding,
                    resolution=RepoBaselineResolution(
                        repository_id=repository.repository_project_id,
                        branch=branch,
                        baseline_ref=baseline or None,
                        error=error,
                    ),
                )
            )
        return results
