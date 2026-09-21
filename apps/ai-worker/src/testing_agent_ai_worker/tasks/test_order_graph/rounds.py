"""测试单图谱任务的轮次编排：写用例文件、按批量切分、组装每轮输入与校验产物。

skill `update-test-case-graph` 每轮只接收四个字段（需求、本轮映射、用例文件路径、历史图谱），
用例正文由它自己按 `case_file_path` 查询，因此这里不做任何正文内联。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from testing_agent_ai_worker.tasks.functional_case_generate.validation import validate_output

GRAPH_SCHEMA_VERSION = "2.0"
# skill 建议的单轮批量起点（不是硬上限），按 case_ids 去重后计数。
GRAPH_BATCH_SIZE = 30
# 本任务在项目工作区下的目录名。
GRAPH_DIR_NAME = "test-case-graph"


def empty_graph() -> dict[str, Any]:
    """空图谱；首轮历史与无可用用例时的产物都是它。"""

    return {"schema_version": GRAPH_SCHEMA_VERSION, "main_paths": [], "edges": []}


def usable_cases(cases: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """筛出可分析用例，返回 (可用用例, 跳过的 case_ids)。

    图谱用例文件要求 `test_steps` 与 `expected_results` 非空；空缺的用例会被跳过，
    因此也不会出现在任何一轮的映射里，否则 skill 的引用校验会失败。
    """

    usable: list[dict[str, Any]] = []
    skipped: list[str] = []
    for case in cases if isinstance(cases, list) else []:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id") or "")
        if not case_id:
            continue
        if not case.get("test_steps") or not case.get("expected_results"):
            skipped.append(case_id)
            continue
        usable.append(case)
    return usable, skipped


def write_cases_file(run_dir: Path, run_id: str, cases: list[dict[str, Any]]) -> Path:
    """写本任务独有的临时用例文件；文件名就是 run_id，内容顶层只有 cases。"""

    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{run_id}.json"
    path.write_text(json.dumps({"cases": cases}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_round_request(run_dir: Path, index: int, payload: dict[str, Any]) -> Path:
    """写本轮请求文件：skill 的 `validate_graph.py --input` 需要一个可读的输入文件。"""

    path = run_dir / f"round-{index}-request.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_round_graph(run_dir: Path, index: int, graph: dict[str, Any]) -> Path:
    """写本轮通过的候选图谱，作为留档与失败重试的依据。"""

    path = run_dir / f"round-{index}-graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def split_batches(links: Any, usable_ids: set[str]) -> list[list[dict[str, Any]]]:
    """把映射切成每轮清单：case_ids 去重后按 GRAPH_BATCH_SIZE 装箱。

    分组只作为装箱边界保留：一轮可以混多个分组，单个分组超过上限时跨轮、
    每轮带同一个 requirement_id；`requirement_id: null` 是未绑定需求用例的分组。
    """

    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    count = 0
    for link in links if isinstance(links, list) else []:
        if not isinstance(link, dict):
            continue
        requirement_id = link.get("requirement_id")
        seen: set[str] = set()
        for case_id in link.get("case_ids") or []:
            if not isinstance(case_id, str) or case_id in seen or case_id not in usable_ids:
                continue
            seen.add(case_id)
            if count == GRAPH_BATCH_SIZE:
                batches.append(current)
                current = []
                count = 0
            item = next(
                (item for item in current if item["requirement_id"] == requirement_id), None
            )
            if item is None:
                item = {"requirement_id": requirement_id, "case_ids": []}
                current.append(item)
            item["case_ids"].append(case_id)
            count += 1
    if current:
        batches.append(current)
    return batches


def build_round_body(
    *,
    payload: dict[str, Any],
    request_path: Path,
    skill_dir: Path,
) -> str:
    """组装本轮 prompt 正文：四个输入字段 + 请求文件与脚本目录的绝对路径。

    正文交给 `run_skill_step` 时它会补上「请先加载本地 skill」前缀，因此这里不重复包装。
    """

    return "\n\n".join(
        [
            json.dumps(payload, ensure_ascii=False, indent=2),
            f"本轮输入已写入 {request_path}，可直接校验："
            f"python3 {skill_dir / 'scripts' / 'validate_graph.py'} "
            f"--input {request_path} --check-input",
            f"用例文件与查询脚本位于 {skill_dir / 'scripts'}，用例文件路径见 case_file_path。",
        ]
    )


def build_retry_suffix(errors: list[str]) -> str:
    """重试时把上一轮的结构校验错误反馈给模型，要求重新输出完整图谱。"""

    detail = "\n".join(f"- {error}" for error in errors[:20])
    return f"\n\n【上一次输出未通过校验，请修正后重新输出完整累计图谱 JSON】\n{detail}"


def parse_graph_text(raw: str, allowed_case_ids: set[str]) -> dict[str, Any]:
    """校验本轮图谱：复用关系产物契约，并要求引用的 case_id 都在用例文件全集内。"""

    canonical = validate_output(
        "relation_analysis", str(raw), expected_case_ids=list(allowed_case_ids)
    )
    return json.loads(canonical)
