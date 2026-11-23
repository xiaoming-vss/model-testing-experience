"""Current-source import previews and commits are atomic and idempotent."""

from copy import deepcopy
from uuid import uuid4

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation import generation_services
from support.generation_candidate_graph import ROOT
from support.generation_import_seed import seed_import_graph

from testing_agent.core.errors import AppError
from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_root_fingerprints import fingerprint_generation_basis
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.ai_generate_import import AiGenerateImport, AiGenerateImportRequest
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_current_chain import delete_chain_storage_for_task
from testing_agent.schemas.generation_candidates import CurrentImportRequest
from testing_agent.services.generation_current_import import CurrentImportCoordinator

SECRET = "test-only-preview-signing-key-32-bytes"
OUTPUT = """cases:
  - module: 登录
    title: 已有用例
    preconditions: 已注册
    steps: 输入密码
    expected_results: 进入首页
    priority: P0
    case_type: smoke
  - module: 注册
    title: 创建账号
    steps: 填写资料
    expected_results: 创建成功
"""


def setup(sync, *, conflict):
    seed_import_graph(sync)
    candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id="d").one()
    slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-d").one()
    source_snapshot = deepcopy(candidate.source_snapshot_json)
    source_snapshot["source"]["instruction"] = "SECRET-PROMPT"
    source_snapshot["source"]["bindings"] = [{"accessToken": "SECRET-TOKEN"}]
    basis = fingerprint_generation_basis(
        kind="function",
        stage="detailed_cases",
        input_snapshot=source_snapshot,
        roots=(ROOT,),
        lineage_hash=candidate.lineage_hash,
        attachment_hashes={},
    )
    for item in (candidate, slot):
        item.content = OUTPUT
        item.format = "yaml"
        item.content_hash = generation_content_hash(OUTPUT, "yaml")
        item.basis_hash = basis
        item.source_snapshot_json = deepcopy(source_snapshot)
    if conflict:
        sync.add(FunctionTestSuite(suite_id="suite-login", requirement_id="req", name="登录"))
        sync.flush()
        sync.add(
            FunctionTestCase(case_id="old", suite_id="suite-login", title="已有用例", module="登录")
        )
    sync.commit()
    session = AsyncSessionAdapter(sync)
    bundle = generation_services(AiGenerateTaskRepository(session))
    return session, CurrentImportCoordinator(bundle.imports, bundle.api_importer)


async def preview(coordinator):
    return await coordinator.preview(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        current_token="current-d",
        target_id="",
        actor_id="u",
        current_root_hashes={ROOT.key: ROOT.content_hash},
        secret=SECRET,
        now=100,
    )


def request(preview, *, confirm, request_id=None):
    return CurrentImportRequest(
        expected_current_token=preview.current_token,
        expected_lineage_hash=preview.full_lineage_hash,
        preview_token=preview.preview_token,
        request_id=request_id or uuid4(),
        confirm_overwrite=confirm,
    )


async def execute(coordinator, body, **overrides):
    params = dict(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        request=body,
        actor_id="u",
        current_root_hashes={ROOT.key: ROOT.content_hash},
        secret=SECRET,
        now=101,
    )
    return await coordinator.execute(**{**params, **overrides})


async def test_conflict_preview_and_atomic_multi_target_import_replay(database):  # noqa: F811
    sync, _, _ = database
    session, coordinator = setup(sync, conflict=True)
    view = await preview(coordinator)
    assert view.requires_confirmation and len(view.conflicts) == 1
    assert view.preview_expires_at == 700
    assert sync.query(FunctionTestSuite).count() == 1
    assert sync.query(AiGenerateImport).count() == 0
    sync.commit()
    request_id = uuid4()
    denied = await execute(coordinator, request(view, confirm=False, request_id=request_id))
    assert denied["requiresConfirmation"] and not denied["imported"]
    sync.commit()
    assert sync.query(AiGenerateImportRequest).count() == 0
    assert sync.query(FunctionTestSuite).count() == 1
    body = request(view, confirm=True, request_id=request_id)
    result = await execute(coordinator, body)
    sync.commit()
    assert result["imported"] and not result["replayed"] and len(result["importRecords"]) == 2
    assert sync.query(FunctionTestSuite).count() == 2 and sync.query(FunctionTestCase).count() == 2
    receipts = sync.query(AiGenerateImport).all()
    assert len(receipts) == 2 and all(item.content == OUTPUT for item in receipts)
    assert all("SECRET-" not in str(item.source_snapshot_json) for item in receipts)
    assert all(
        item.source_candidate_id == "d" and item.lineage_hash == view.full_lineage_hash
        for item in receipts
    )
    assert {item.effective_import_id for item in sync.query(FunctionTestSuite).all()} == {
        item.import_id for item in receipts
    }
    replay = await execute(coordinator, body, current_root_hashes={})
    sync.commit()
    assert replay["replayed"] and replay["importRecords"] == result["importRecords"]
    assert sync.query(AiGenerateImport).count() == 2 and sync.query(FunctionTestCase).count() == 2
    with pytest.raises(AppError, match="请求标识"):
        await execute(coordinator, body.model_copy(update={"confirm_overwrite": False}))
    sync.rollback()
    await delete_chain_storage_for_task(session, task_id="task")
    sync.commit()
    assert sync.query(AiGenerationCandidate).filter_by(candidate_id="d").count() == 0
    assert sync.query(AiGenerateImport).count() == 2 and sync.query(FunctionTestCase).count() == 2
    retained = sync.query(AiGenerateImport).first().source_snapshot_json["upstreamOutputs"]
    assert {item["content"] for item in retained} == {"content-m", "content-a", "content-p"}
    replay_after_cleanup = await execute(coordinator, body, current_root_hashes={})
    assert replay_after_cleanup["replayed"]
    assert replay_after_cleanup["importRecords"] == result["importRecords"]
    read_only_replay = await coordinator.replay(
        requirement_id="req", kind="function", stage="detailed_cases", request=body, actor_id="u"
    )
    assert read_only_replay == replay_after_cleanup
    with pytest.raises(AppError, match="请求标识"):
        await coordinator.replay(
            requirement_id="req",
            kind="function",
            stage="detailed_cases",
            request=body,
            actor_id="other",
        )
    assert (
        await coordinator.replay(
            requirement_id="req",
            kind="function",
            stage="detailed_cases",
            request=body.model_copy(update={"request_id": uuid4()}),
            actor_id="u",
        )
        is None
    )


async def test_empty_target_preview_never_creates_suites(database):  # noqa: F811
    sync, _, _ = database
    _, coordinator = setup(sync, conflict=False)
    view = await preview(coordinator)
    assert not view.requires_confirmation and view.conflicts == []
    assert sync.query(FunctionTestSuite).count() == 0
    assert sync.query(AiGenerateImportRequest).count() == 0


async def test_target_change_or_stale_source_prevents_all_writes(database):  # noqa: F811
    sync, _, _ = database
    _, coordinator = setup(sync, conflict=True)
    view = await preview(coordinator)
    sync.commit()
    sync.query(FunctionTestCase).filter_by(case_id="old").one().title = "modified"
    sync.commit()
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await execute(coordinator, request(view, confirm=True))
    sync.commit()
    assert sync.query(AiGenerateImportRequest).count() == 0
    assert sync.query(FunctionTestSuite).count() == 1
    assert sync.query(FunctionTestCase).count() == 1


@pytest.mark.parametrize(
    ("kind", "stage", "output"),
    [
        (
            "api",
            "generate",
            """cases:
  - name: login
    method: GET
    urlTemplate: /login
    bodyType: none
""",
        ),
        (
            "ui",
            "ui_yaml",
            """- name: Login
  enabled: true
  orderNo: 1
  stepsJson:
  - orderNo: 1
    stepName: Open
    keyword: open
    operationValue: https://example.test/
    continueOnFailure: false
    enabled: true
""",
        ),
    ],
)
async def test_api_and_ui_import_use_current_without_attempt_dependency(
    database,  # noqa: F811
    kind,
    stage,
    output,
):
    from support.generation_import_seed import seed_api_or_ui_import_graph

    from testing_agent.models.api_case import ApiCase
    from testing_agent.models.api_collection import ApiCollection
    from testing_agent.models.ui_test_case import UiTestCase
    from testing_agent.models.ui_test_suite import UiTestSuite

    sync, _, _ = database
    root = seed_api_or_ui_import_graph(sync, kind, output)
    if kind == "api":
        sync.add(
            ApiCollection(collection_id="target", project_id="p", requirement_id="req", name="api")
        )
    else:
        sync.add(UiTestSuite(suite_id="target", project_id="p", requirement_id="req", name="ui"))
    sync.commit()
    session = AsyncSessionAdapter(sync)
    bundle = generation_services(AiGenerateTaskRepository(session))
    coordinator = CurrentImportCoordinator(bundle.imports, bundle.api_importer)
    view = await coordinator.preview(
        requirement_id="req",
        kind=kind,
        stage=stage,
        current_token=f"{kind}-current-2",
        target_id="target",
        actor_id="u",
        current_root_hashes={root.key: root.content_hash},
        secret=SECRET,
        now=100,
    )
    assert not view.requires_confirmation
    assert sync.query(ApiCase if kind == "api" else UiTestCase).count() == 0
    sync.commit()
    body = CurrentImportRequest(
        expected_current_token=view.current_token,
        expected_lineage_hash=view.full_lineage_hash,
        preview_token=view.preview_token,
        request_id=uuid4(),
        target_id="target",
    )
    result = await coordinator.execute(
        requirement_id="req",
        kind=kind,
        stage=stage,
        request=body,
        actor_id="u",
        current_root_hashes={root.key: root.content_hash},
        secret=SECRET,
        now=101,
    )
    sync.commit()
    assert result["imported"] and len(result["importRecords"]) == 1
    receipt = sync.query(AiGenerateImport).one()
    assert (
        receipt.source_attempt_id is None and receipt.source_candidate_id == f"{kind}-candidate-2"
    )
    assert sync.query(ApiCase if kind == "api" else UiTestCase).count() == 1
    target = (
        sync.query(ApiCollection if kind == "api" else UiTestSuite)
        .filter_by(**({"collection_id": "target"} if kind == "api" else {"suite_id": "target"}))
        .one()
    )
    assert target.effective_import_id == receipt.import_id


async def test_import_failure_after_receipts_rolls_back_all_targets(database, monkeypatch):  # noqa: F811
    from testing_agent.services import generation_current_import as current_import

    sync, _, _ = database
    _, coordinator = setup(sync, conflict=True)
    view = await preview(coordinator)
    sync.commit()
    previous_content = deepcopy(
        sync.query(FunctionTestCase).filter_by(case_id="old").one().content_json
    )
    original = current_import.record_current_import

    async def fail_after_receipts(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("simulated receipt failure")

    monkeypatch.setattr(current_import, "record_current_import", fail_after_receipts)
    with pytest.raises(RuntimeError, match="simulated"):
        await execute(coordinator, request(view, confirm=True))
    sync.commit()  # Catching a failure must not make a partial import committable.
    assert sync.query(FunctionTestSuite).count() == 1
    assert sync.query(FunctionTestCase).count() == 1
    assert (
        sync.query(FunctionTestCase).filter_by(case_id="old").one().content_json == previous_content
    )
    assert sync.query(AiGenerateImportRequest).count() == 0
    assert sync.query(AiGenerateImport).count() == 0
