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

import pytest
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.code_risk_analysis import (  # noqa: F401
    RISK_REPORT_YAML,
    approved_understanding,
    dump_code_risk_analysis_run,
    make_run,
    worker_contract_authority,
)

from testing_agent.schemas.workers import WorkerTaskEventRequest
from testing_agent.services.code_risk_analysis import (
    parse_risk_report,
)
from testing_agent.services.worker import apply_ai_completion_to_run


def test_parse_risk_report_reads_context_preview_receipt():
    report = parse_risk_report(
        """\
analyzedAt: "2026-08-27T10:00:00Z"
contextReceipt:
  mode: context_preview
  repositories:
    - repositoryId: "repo-1"
      headCommit: "def456"
  counts:
    repositories: 1
    changedFiles: 2
    diffChars: 123
  truncatedFiles: ["src/big.py"]
  summary: "已读取仓库上下文"
  filesRead: ["src/login.py"]
  toolsUsed: ["read"]
"""
    )

    assert report["analyzedAt"] == "2026-08-27T10:00:00Z"
    assert report["repositories"] == [{"repositoryId": "repo-1", "headCommit": "def456"}]
    assert report["contextReceipt"]["mode"] == "context_preview"
    assert report["contextReceipt"]["counts"]["diffChars"] == 123
    assert report["contextReceipt"]["truncatedFiles"] == ["src/big.py"]
    assert report["contextReceipt"]["summary"] == "已读取仓库上下文"
    assert "risks" not in report

    snake = parse_risk_report("context_receipt:\n  summary: snake\n")
    assert snake["contextReceipt"]["summary"] == "snake"
    assert snake["repositories"] == []


def test_parse_risk_report_rejects_malformed_context_receipt():
    for raw in (
        "contextReceipt: []\n",
        "contextReceipt:\n  repositories: not-a-list\n",
        "contextReceipt:\n  repositories:\n    - not-an-object\n",
        "analyzedAt: 2026-08-27\ncontextReceipt: {}\n",
    ):
        assert parse_risk_report(raw) is None


def test_dump_code_risk_analysis_run_includes_context_receipt():
    receipt_yaml = (
        "analyzedAt: '2026-08-27T10:00:00Z'\n"
        "contextReceipt:\n"
        "  mode: context_preview\n"
        "  repositories: []\n"
        "  counts: {repositories: 0}\n"
        "  summary: preview\n"
    )
    payload = dump_code_risk_analysis_run(make_run(status="success", result_yaml=receipt_yaml))

    assert payload["report"]["contextReceipt"]["mode"] == "context_preview"
    assert payload["report"]["repositories"] == []


def test_parse_risk_report_full_structure():
    report = parse_risk_report(RISK_REPORT_YAML)

    assert report["analyzedAt"] == "2026-08-21T10:30:00Z"
    assert report["repositories"] == [
        {
            "repositoryId": "repo-1",
            "branch": "develop",
            "baselineCommit": "abc123",
            "headCommit": "def456",
        }
    ]
    assert report["changeOverview"] == {"filesChanged": 12, "additions": 340, "deletions": 120}
    assert report["risks"][0]["level"] == "high"
    assert report["affectedCases"][0]["caseId"] == "ac-1"
    assert report["coverageGaps"][0]["suggestion"] == "新增失败路径用例"


def test_parse_risk_report_accepts_snake_case_aliases():
    report = parse_risk_report(
        """\
analyzed_at: "2026-08-21T10:30:00Z"
repositories:
  - repository_id: "repo-2"
    branch: "main"
    baseline_commit: "111"
    head_commit: "222"
change_overview:
  filesChanged: 1
risk_list:
  - level: "low"
    reason: "小改动"
affected_cases:
  - caseId: "fc-1"
coverage_gaps:
  - gap: "缺口"
"""
    )

    assert report["analyzedAt"] == "2026-08-21T10:30:00Z"
    assert report["repositories"] == [
        {
            "repositoryId": "repo-2",
            "branch": "main",
            "baselineCommit": "111",
            "headCommit": "222",
        }
    ]
    assert report["changeOverview"] == {"filesChanged": 1}
    assert report["risks"] == [{"level": "low", "reason": "小改动"}]
    assert report["affectedCases"] == [{"caseId": "fc-1"}]
    assert report["coverageGaps"] == [{"gap": "缺口"}]


def test_parse_risk_report_repository_normalizes_keys_and_keeps_extra_fields():
    report = parse_risk_report(
        """\
repositories:
  - repository_id: "repo-3"
    baseline_commit: "aaa"
    head_commit: "bbb"
    note: "保留字段"
"""
    )

    assert report["repositories"] == [
        {"repositoryId": "repo-3", "baselineCommit": "aaa", "headCommit": "bbb", "note": "保留字段"}
    ]


def test_parse_risk_report_rejects_non_string_analyzed_at():
    # 契约要求 analyzedAt 为字符串;未加引号的时间戳被 YAML 解析为 datetime,
    # 属形态不符,整体返回 None 而非静默改写格式。
    assert parse_risk_report("analyzedAt: 2026-08-21T10:30:00Z\nrisks: []\n") is None


def test_parse_risk_report_rejects_wrong_shaped_section():
    assert parse_risk_report('risks: "not-a-list"\n') is None
    assert parse_risk_report("changeOverview:\n  - not-an-object\n") is None
    assert parse_risk_report("repositories:\n  - not-an-object\n") is None


def test_parse_risk_report_fills_missing_sections_with_none():
    report = parse_risk_report('risks:\n  - level: "high"\n')

    assert report["risks"] == [{"level": "high"}]
    assert report["analyzedAt"] is None
    assert report["repositories"] == []
    assert report["changeOverview"] is None
    assert report["affectedCases"] is None
    assert report["coverageGaps"] is None


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "cases: []", "- a\n- b", "not: [valid", "just a string"],
)
def test_parse_risk_report_returns_none_when_empty_or_unrecognized(raw):
    assert parse_risk_report(raw) is None


def test_dump_code_risk_analysis_run_includes_parsed_report():
    run = make_run(status="success", result_yaml=RISK_REPORT_YAML)

    payload = dump_code_risk_analysis_run(run)

    assert payload["resultYaml"] == RISK_REPORT_YAML
    report = payload["report"]
    assert report["analyzedAt"] == "2026-08-21T10:30:00Z"
    assert report["repositories"][0]["baselineCommit"] == "abc123"
    assert report["repositories"][0]["headCommit"] == "def456"
    assert report["changeOverview"]["filesChanged"] == 12
    assert report["risks"][0]["level"] == "high"
    assert report["affectedCases"][0]["caseId"] == "ac-1"
    assert report["coverageGaps"][0]["gap"] == "登录失败路径无用例覆盖"


def test_completion_callback_persists_report_readable_via_detail_dump():
    run = make_run(status="success", result_yaml="")
    body = WorkerTaskEventRequest(
        workerId="worker-1",
        taskId="task-1",
        runId="run-1",
        status="success",
        resultYaml=RISK_REPORT_YAML,
    )

    apply_ai_completion_to_run(run, body)

    assert run.result_yaml == RISK_REPORT_YAML
    payload = dump_code_risk_analysis_run(run)
    assert payload["status"] == "success"
    assert payload["report"]["repositories"][0]["headCommit"] == "def456"
    assert payload["report"]["analyzedAt"] == "2026-08-21T10:30:00Z"


def test_completion_callback_reads_report_from_snapshot_fallback():
    run = make_run(status="success", result_yaml="")
    apply_ai_completion_to_run(
        run,
        WorkerTaskEventRequest(
            workerId="worker-1",
            status="success",
            snapshotJson={"resultYaml": RISK_REPORT_YAML},
        ),
    )

    assert dump_code_risk_analysis_run(run)["report"]["risks"][0]["level"] == "high"
