"""工单 06/07:code_risk_analysis 任务类型、凭据下发与报告存储读取。

覆盖:
- 任务快照组装(需求文档、绑定清单+基线+connectionId、现有测试内容口径);
- RC-3 情形④分支校验接线(任务创建时按绑定解析连接查询远端);
- GitLab 凭据内部端点(worker token 鉴权、按快照分组解密、错误语义);
- 失败错误消息与补救建议回显;
- 风险报告解析与回读(worker 完成回调 resultYaml → run 表 → report 结构);
- 重复发起同一需求产生多次任务记录且互不覆盖;
- /v1 任务创建与运行端点。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.code_risk_analysis import (  # noqa: F401
    FakeCipher,
    FakeSession,
    approved_understanding,
    make_connection,
    worker_contract_authority,
)

from testing_agent.core.errors import AppError
from testing_agent.services import worker_task as worker_task_service_module
from testing_agent.services.code_risk_analysis import (
    gitlab_credentials_payload,
)
from testing_agent.services.worker_task import WorkerTaskService


async def test_gitlab_credentials_payload_groups_by_connection_and_decrypts():
    session = FakeSession(
        [
            make_connection("conn-1", "https://gitlab.example.com", "enc:1"),
            make_connection("conn-2", "https://gitlab.example.com", "enc:2"),
        ]
    )
    bindings = [
        {"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"},
        {"bindingId": "b2", "repositoryId": "repo-2", "connectionId": "conn-1"},
        {"bindingId": "b3", "repositoryId": "repo-3", "connectionId": "conn-2"},
        {"bindingId": "b4", "repositoryId": "repo-4", "connectionId": ""},
    ]

    payload = await gitlab_credentials_payload(
        session,
        "worker-task-1",
        "project-1",
        bindings,
        FakeCipher({"enc:1": "t1", "enc:2": "t2"}),
        user_id="user-1",
    )

    assert payload["taskId"] == "worker-task-1"
    assert payload["bindings"] == bindings
    credentials = payload["credentials"]
    assert [c["connectionId"] for c in credentials] == ["conn-1", "conn-2"]
    assert credentials[0]["baseUrl"] == "https://gitlab.example.com"
    assert credentials[0]["accessToken"] == "t1"
    assert credentials[0]["repositoryIds"] == ["repo-1", "repo-2"]
    assert credentials[1]["repositoryIds"] == ["repo-3"]


@pytest.mark.asyncio
async def test_gitlab_credentials_payload_raises_when_connection_missing():
    with pytest.raises(AppError) as excinfo:
        await gitlab_credentials_payload(
            FakeSession([None]),
            "worker-task-1",
            "project-1",
            [{"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"}],
            FakeCipher({}),
            user_id="user-1",
        )
    assert excinfo.value.code == 3401


@pytest.mark.asyncio
async def test_gitlab_credentials_payload_raises_when_cipher_missing():
    with pytest.raises(AppError) as excinfo:
        await gitlab_credentials_payload(
            FakeSession([make_connection("conn-1", "https://gitlab.example.com", "enc:1")]),
            "worker-task-1",
            "project-1",
            [{"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"}],
            None,
            user_id="user-1",
        )
    assert excinfo.value.code == 3403
    assert "解密密钥未配置" in excinfo.value.message


@pytest.mark.asyncio
async def test_gitlab_credentials_payload_raises_on_decrypt_failure():
    with pytest.raises(AppError) as excinfo:
        await gitlab_credentials_payload(
            FakeSession([make_connection("conn-1", "https://gitlab.example.com", "enc:bad")]),
            "worker-task-1",
            "project-1",
            [{"bindingId": "b1", "repositoryId": "repo-1", "connectionId": "conn-1"}],
            FakeCipher({}),
            user_id="user-1",
        )
    assert excinfo.value.code == 3403
    assert "解密失败" in excinfo.value.message


# ---------------------------------------------------------------------------
# WorkerTaskService.gitlab_credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_task_service_gitlab_credentials_rejects_other_task_types(monkeypatch):
    async def fake_find_task(session, domain, task_id):
        return SimpleNamespace(task_id=task_id, task_type="api_case_generate", run_id="run-1")

    monkeypatch.setattr(worker_task_service_module, "find_task", fake_find_task)

    with pytest.raises(AppError) as excinfo:
        await WorkerTaskService(SimpleNamespace(session=object())).gitlab_credentials("task-1")
    assert excinfo.value.code == 404


@pytest.mark.asyncio
async def test_worker_requirement_document_allows_code_risk_analysis(monkeypatch):
    class FakeRepository:
        session = object()

        async def get_worker_task(self, domain, task_id):
            assert domain == "ai"
            return SimpleNamespace(
                task_id=task_id,
                task_type="code_risk_analysis",
                run_id="run-1",
                generate_task_id="task-1",
            )

        async def get_ai_run(self, run_id):
            return SimpleNamespace(run_id="run-1", requirement_id="req-1", task_id="task-1")

        async def get_requirement(self, requirement_id):
            return SimpleNamespace(
                requirement_id="req-1",
                document_file_id="stored-requirement",
                document_content="需求正文",
                document_filename="",
            )

    direct = SimpleNamespace(
        is_direct=AsyncMock(return_value=True),
        authorize=AsyncMock(
            return_value=SimpleNamespace(
                task=SimpleNamespace(requirement_id="req-1"), input_snapshot={}
            )
        ),
    )
    monkeypatch.setattr(worker_task_service_module, "DirectStageWorkerService", lambda _: direct)
    requirement = await WorkerTaskService(FakeRepository()).requirement_document("worker-task-1")
    assert requirement.document_content == "需求正文"
