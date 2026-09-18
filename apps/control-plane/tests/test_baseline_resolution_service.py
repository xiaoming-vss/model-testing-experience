"""工单 05:基线解析服务(RC-3)。

覆盖五种情形与验收标准:
- ① 手工基线分支直接使用,不查历史,解析结果不随历史绑定变化;
- ② 自动查找之前迭代最近一次绑定(迭代按结束时间排序,空则创建时间);
- ③ 从未绑定 → 无基线;本迭代与之后迭代的绑定不作基线;
- ④ 查找失败(分支已删、远端异常、绑定数据缺失)→ 结构化错误提示手工指定;
- ⑤ 命中迭代多条绑定取创建时间最新并标注;多仓库按仓库独立解析。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from testing_agent.core.errors import AppError, ErrNotFound
from testing_agent.repositories.resource_binding import RepoBindingWithSprint
from testing_agent.services.baseline_resolution import (
    BaselineResolutionService,
    RepoBaselineResolution,
)


def _sprint(sprint_id: str, **overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "sprint_id": sprint_id,
        "project_id": "project-1",
        "end_time": datetime(2026, 8, 1, 12),
        "created_at": datetime(2026, 7, 1, 12),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _repo_binding(
    repository_id: str,
    branch: str,
    created_at: datetime,
    *,
    pk: int = 1,
    extra: dict[str, str] | None = None,
) -> SimpleNamespace:
    extra_json: dict[str, str] = {"branch": branch, **(extra or {})}
    return SimpleNamespace(
        id=pk,
        binding_id=f"b-{pk}",
        remote_resource_id=repository_id,
        extra_json=extra_json,
        created_at=created_at,
    )


_UNSET = object()


class FakeBindingRepository:
    def __init__(
        self,
        *,
        requirement: Any = _UNSET,
        sprint: Any = _UNSET,
        current_bindings: list | None = None,
        history: list | None = None,
        sprint_bindings: list | None = None,
    ) -> None:
        if requirement is _UNSET:
            requirement = SimpleNamespace(requirement_id="req-1", sprint_id="sprint-3")
        if sprint is _UNSET:
            sprint = _sprint("sprint-3", end_time=datetime(2026, 8, 10, 12))
        self.requirement = requirement
        self.sprint = sprint
        self.current_bindings = list(current_bindings) if current_bindings else []
        self.history = list(history) if history else []
        self.sprint_bindings = list(sprint_bindings) if sprint_bindings else []
        self.history_calls = 0
        self.sprint_binding_calls = 0

    async def get_requirement(self, requirement_id: str):
        if self.requirement is None or requirement_id != self.requirement.requirement_id:
            return None
        return self.requirement

    async def get_sprint(self, sprint_id: str):
        if self.sprint is None or sprint_id != self.sprint.sprint_id:
            return None
        return self.sprint

    async def list_active_repo_bindings_for_requirement(self, requirement_id: str):
        return self.current_bindings

    async def list_active_repo_bindings_for_sprint(self, sprint_id: str):
        self.sprint_binding_calls += 1
        return self.sprint_bindings

    async def list_active_repo_bindings_with_sprint_for_project(self, project_id: str):
        self.history_calls += 1
        return self.history


class FakeSprintRepository:
    def __init__(self, sprints: list | None = None) -> None:
        self.sprints = list(sprints) if sprints else []
        self.list_calls = 0

    async def list_active_by_project(self, project_id: str):
        self.list_calls += 1
        return self.sprints


class FakeChecker:
    """分支存在性检查器:result 为 False/True/异常。"""

    def __init__(self, result: bool | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, repository_id: str, branch: str) -> bool:
        self.calls.append((repository_id, branch))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _service(
    binding_repo: FakeBindingRepository,
    sprint_repo: FakeSprintRepository | None = None,
    checker: FakeChecker | None = None,
) -> BaselineResolutionService:
    return BaselineResolutionService(binding_repo, sprint_repo or FakeSprintRepository(), checker)


async def test_manual_baseline_used_directly_without_history_lookup():
    """情形①:手工基线直接使用,不查历史、不校验远端。"""
    checker = FakeChecker(True)
    binding = _repo_binding(
        "repo-1", "feat", datetime(2026, 8, 9), extra={"baseline_branch": "main"}
    )
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    repo = FakeBindingRepository(
        current_bindings=[binding],
        history=[
            RepoBindingWithSprint(_repo_binding("repo-1", "release-1", datetime(2026, 7, 20)), s1)
        ],
    )
    sprint_repo = FakeSprintRepository([s1, repo.sprint])

    results = await _service(repo, sprint_repo, checker).resolve_for_requirement("req-1")

    assert len(results) == 1
    assert results[0].baseline_ref == "main"
    assert results[0].error == ""
    assert checker.calls == []
    # 全部为手工基线:历史与迭代列表均不查询。
    assert repo.history_calls == 0
    assert sprint_repo.list_calls == 0


async def test_manual_baseline_stable_when_history_changes():
    """手工基线设置后,解析结果不随历史绑定变化。"""
    binding = _repo_binding(
        "repo-1", "feat", datetime(2026, 8, 9), extra={"baseline_branch": "main"}
    )
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    repo = FakeBindingRepository(current_bindings=[binding])
    sprint_repo = FakeSprintRepository([s1, repo.sprint])

    first = await _service(repo, sprint_repo).resolve_for_requirement("req-1")
    repo.history = [
        RepoBindingWithSprint(_repo_binding("repo-1", "release-9", datetime(2026, 8, 8), pk=1), s1)
    ]
    second = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert first == second
    assert first[0].baseline_ref == "main"


async def test_auto_resolve_picks_most_recent_previous_sprint():
    """情形②:取之前迭代中最近一次绑定的分支。"""
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    s2 = _sprint("sprint-2", end_time=datetime(2026, 8, 6))
    current = _sprint("sprint-3", end_time=datetime(2026, 8, 10))
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "release-1", datetime(2026, 7, 20), pk=1), s1
        ),
        RepoBindingWithSprint(_repo_binding("repo-1", "release-2", datetime(2026, 8, 4), pk=2), s2),
    ]
    repo = FakeBindingRepository(sprint=current, current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([s1, s2, current])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref == "release-2"
    assert results[0].note == ""
    assert results[0].error == ""


async def test_sprint_without_end_time_sorted_by_created_at():
    """迭代排序:结束时间为空时按创建时间参与排序。"""
    current = _sprint("sprint-3", end_time=None, created_at=datetime(2026, 8, 10))
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 5), created_at=datetime(2026, 7, 1))
    s2 = _sprint("sprint-2", end_time=None, created_at=datetime(2026, 8, 8))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    history = [
        RepoBindingWithSprint(_repo_binding("repo-1", "release-1", datetime(2026, 8, 1), pk=1), s1),
        RepoBindingWithSprint(_repo_binding("repo-1", "release-2", datetime(2026, 8, 6), pk=2), s2),
    ]
    repo = FakeBindingRepository(sprint=current, current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([s1, s2, current])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref == "release-2"


async def test_equal_end_time_sibling_ordered_by_created_at():
    """结束时间相同时按创建时间分先后:创建更早的同刻结束迭代属于之前迭代。"""
    current = _sprint("sprint-3", end_time=datetime(2026, 8, 10), created_at=datetime(2026, 8, 9))
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 10), created_at=datetime(2026, 8, 1))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    history = [
        RepoBindingWithSprint(_repo_binding("repo-1", "release-1", datetime(2026, 8, 2), pk=1), s1),
    ]
    repo = FakeBindingRepository(sprint=current, current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([s1, current])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref == "release-1"


async def test_never_bound_returns_no_baseline():
    """情形③:该仓库从未被绑定 → 无基线。"""
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    repo = FakeBindingRepository(current_bindings=[binding])

    results = await _service(repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref is None
    assert results[0].error == ""
    assert results[0].note == ""


async def test_current_sprint_bindings_not_used_as_baseline():
    """本迭代内其他需求的绑定不作基线。"""
    current = _sprint("sprint-3", end_time=datetime(2026, 8, 10))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "other-req-branch", datetime(2026, 8, 9, 1)), current
        ),
    ]
    repo = FakeBindingRepository(sprint=current, current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([current])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref is None


async def test_previous_binding_wins_over_newer_current_binding():
    """本迭代绑定虽更新,基线仍取之前迭代的绑定。"""
    current = _sprint("sprint-3", end_time=datetime(2026, 8, 10))
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "release-1", datetime(2026, 7, 20), pk=1), s1
        ),
        RepoBindingWithSprint(
            _repo_binding("repo-1", "cur-branch", datetime(2026, 8, 9, 5), pk=2), current
        ),
    ]
    repo = FakeBindingRepository(sprint=current, current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([s1, current])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref == "release-1"


async def test_future_sprint_bindings_excluded():
    """查找范围严格限于之前迭代:之后迭代的绑定不参与。"""
    current = _sprint("sprint-3", end_time=datetime(2026, 8, 10))
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    s4 = _sprint("sprint-4", end_time=datetime(2026, 8, 30))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "release-1", datetime(2026, 7, 20), pk=1), s1
        ),
        RepoBindingWithSprint(
            _repo_binding("repo-1", "future-branch", datetime(2026, 8, 20), pk=2), s4
        ),
    ]
    repo = FakeBindingRepository(sprint=current, current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([s1, current, s4])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref == "release-1"


async def test_deleted_branch_returns_structured_error():
    """情形④:基线分支已删除 → 结构化错误并提示手工指定。"""
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "release-1", datetime(2026, 7, 20), pk=1), s1
        ),
    ]
    checker = FakeChecker(False)
    repo = FakeBindingRepository(current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([s1, repo.sprint])

    results = await _service(repo, sprint_repo, checker).resolve_for_requirement("req-1")

    assert results[0].baseline_ref is None
    assert "手工指定" in results[0].error
    assert "release-1" in results[0].error
    assert checker.calls == [("repo-1", "release-1")]


async def test_branch_check_failure_returns_structured_error():
    """情形④:远端校验异常 → 结构化错误并提示手工指定。"""
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "release-1", datetime(2026, 7, 20), pk=1), s1
        ),
    ]
    checker = FakeChecker(RuntimeError("boom"))
    repo = FakeBindingRepository(current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([s1, repo.sprint])

    results = await _service(repo, sprint_repo, checker).resolve_for_requirement("req-1")

    assert results[0].baseline_ref is None
    assert "手工指定" in results[0].error
    assert "boom" in results[0].error


async def test_history_binding_without_branch_returns_error():
    """情形④:最近一次绑定数据缺失分支 → 结构化错误并提示手工指定。"""
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    broken = SimpleNamespace(
        id=1,
        binding_id="b-1",
        remote_resource_id="repo-1",
        extra_json={},
        created_at=datetime(2026, 7, 20),
    )
    repo = FakeBindingRepository(
        current_bindings=[binding], history=[RepoBindingWithSprint(broken, s1)]
    )
    sprint_repo = FakeSprintRepository([s1, repo.sprint])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref is None
    assert "手工指定" in results[0].error


async def test_multiple_bindings_in_hit_sprint_take_latest_created_at_with_note():
    """情形⑤:命中迭代多条绑定,取创建时间最新并标注。"""
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "release-old", datetime(2026, 7, 20), pk=1), s1
        ),
        RepoBindingWithSprint(
            _repo_binding("repo-1", "release-new", datetime(2026, 7, 22), pk=2), s1
        ),
    ]
    repo = FakeBindingRepository(current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([s1, repo.sprint])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref == "release-new"
    assert "多条绑定" in results[0].note
    assert results[0].error == ""


async def test_multiple_bindings_same_created_at_take_latest_pk():
    """创建时间相同时取 id 较大的一条,结果确定。"""
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    same_time = datetime(2026, 7, 20)
    history = [
        RepoBindingWithSprint(_repo_binding("repo-1", "release-a", same_time, pk=1), s1),
        RepoBindingWithSprint(_repo_binding("repo-1", "release-b", same_time, pk=2), s1),
    ]
    repo = FakeBindingRepository(current_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([s1, repo.sprint])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert results[0].baseline_ref == "release-b"
    assert "多条绑定" in results[0].note


async def test_repositories_resolved_independently():
    """同一需求多仓库按仓库独立解析,结果顺序与绑定顺序一致。"""
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    repo1 = _repo_binding("repo-1", "feat", datetime(2026, 8, 9), pk=1)
    repo2 = _repo_binding(
        "repo-2", "feat", datetime(2026, 8, 9), pk=2, extra={"baseline_branch": "main"}
    )
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "release-1", datetime(2026, 7, 20), pk=1), s1
        ),
    ]
    repo = FakeBindingRepository(current_bindings=[repo1, repo2], history=history)
    sprint_repo = FakeSprintRepository([s1, repo.sprint])

    results = await _service(repo, sprint_repo).resolve_for_requirement("req-1")

    assert [r.repository_id for r in results] == ["repo-1", "repo-2"]
    assert results[0].baseline_ref == "release-1"
    assert results[1].baseline_ref == "main"


async def test_current_binding_without_branch_returns_error():
    """当前绑定缺少分支信息 → 结构化错误并提示手工指定。"""
    broken = SimpleNamespace(
        id=1,
        binding_id="b-1",
        remote_resource_id="repo-1",
        extra_json={},
        created_at=datetime(2026, 8, 9),
    )
    repo = FakeBindingRepository(current_bindings=[broken])

    results = await _service(repo).resolve_for_requirement("req-1")

    assert results[0].repository_id == "repo-1"
    assert results[0].branch == ""
    assert results[0].baseline_ref is None
    assert "手工指定" in results[0].error


async def test_requirement_not_found_raises():
    repo = FakeBindingRepository(requirement=None)
    with pytest.raises(AppError) as exc_info:
        await _service(repo).resolve_for_requirement("req-x")
    assert exc_info.value.code == ErrNotFound.code


async def test_sprint_not_found_raises():
    repo = FakeBindingRepository(sprint=None)
    with pytest.raises(AppError) as exc_info:
        await _service(repo).resolve_for_requirement("req-1")
    assert exc_info.value.code == ErrNotFound.code


async def test_no_bindings_returns_empty_list():
    repo = FakeBindingRepository(current_bindings=[])
    results = await _service(repo).resolve_for_requirement("req-1")
    assert results == []


def test_dump_payload_keys():
    result = RepoBaselineResolution("repo-1", "feat", baseline_ref="main", note="n", error="e")
    assert result.dump() == {
        "repositoryId": "repo-1",
        "branch": "feat",
        "baselineRef": "main",
        "note": "n",
        "error": "e",
    }


# ---------------------------------------------------------------------------
# resolve_for_sprint(工单 08:迭代代码概览复用口径)
# ---------------------------------------------------------------------------


async def test_resolve_for_sprint_manual_bindings_skip_history():
    """迭代级解析:全部手工基线时不查迭代列表与项目历史。"""
    binding = _repo_binding(
        "repo-1", "feat", datetime(2026, 8, 9), extra={"baseline_branch": "main"}
    )
    repo = FakeBindingRepository(
        sprint=_sprint("sprint-3", end_time=datetime(2026, 8, 10)),
        sprint_bindings=[binding],
    )
    sprint_repo = FakeSprintRepository([repo.sprint])

    results = await _service(repo, sprint_repo).resolve_for_sprint("sprint-3")

    assert len(results) == 1
    assert results[0].binding is binding
    assert results[0].resolution.baseline_ref == "main"
    assert repo.history_calls == 0
    assert sprint_repo.list_calls == 0


async def test_resolve_for_sprint_auto_baseline_queries_history_once():
    """迭代级解析:自动查找时迭代列表与项目历史各查询一次,规则与逐需求一致。"""
    current = _sprint("sprint-3", end_time=datetime(2026, 8, 10))
    s1 = _sprint("sprint-1", end_time=datetime(2026, 8, 1))
    binding1 = _repo_binding("repo-1", "feat", datetime(2026, 8, 9), pk=1)
    binding2 = _repo_binding("repo-2", "feat", datetime(2026, 8, 9, 1), pk=2)
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "release-1", datetime(2026, 7, 20), pk=1), s1
        ),
        RepoBindingWithSprint(
            _repo_binding("repo-2", "release-2", datetime(2026, 7, 21), pk=2), s1
        ),
    ]
    repo = FakeBindingRepository(
        sprint=current,
        sprint_bindings=[binding2, binding1],
        history=history,
    )
    sprint_repo = FakeSprintRepository([s1, current])

    results = await _service(repo, sprint_repo).resolve_for_sprint("sprint-3")

    assert [row.binding.remote_resource_id for row in results] == ["repo-2", "repo-1"]
    assert [row.resolution.baseline_ref for row in results] == ["release-2", "release-1"]
    assert repo.history_calls == 1
    assert sprint_repo.list_calls == 1
    assert repo.sprint_binding_calls == 1


async def test_resolve_for_sprint_current_sprint_bindings_not_baselines():
    """迭代级解析:本迭代内绑定不作基线(与 RC-3 口径一致)。"""
    current = _sprint("sprint-3", end_time=datetime(2026, 8, 10))
    binding = _repo_binding("repo-1", "feat", datetime(2026, 8, 9))
    history = [
        RepoBindingWithSprint(
            _repo_binding("repo-1", "cur-branch", datetime(2026, 8, 9, 5), pk=2), current
        ),
    ]
    repo = FakeBindingRepository(sprint=current, sprint_bindings=[binding], history=history)
    sprint_repo = FakeSprintRepository([current])

    results = await _service(repo, sprint_repo).resolve_for_sprint("sprint-3")

    assert results[0].resolution.baseline_ref is None
    assert results[0].resolution.error == ""


async def test_resolve_for_sprint_without_bindings_returns_empty():
    repo = FakeBindingRepository(sprint_bindings=[])
    results = await _service(repo).resolve_for_sprint("sprint-3")
    assert results == []
    assert repo.history_calls == 0


async def test_resolve_for_sprint_missing_sprint_raises():
    repo = FakeBindingRepository(sprint=None)
    with pytest.raises(AppError) as exc_info:
        await _service(repo).resolve_for_sprint("sprint-x")
    assert exc_info.value.code == ErrNotFound.code
