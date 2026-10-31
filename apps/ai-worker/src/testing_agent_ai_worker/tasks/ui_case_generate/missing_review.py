"""Review fillability against unchanged inputs; never rewrite candidate YAML."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import traceback
from pathlib import Path
from typing import Any, Callable, Literal, TypedDict

from ..output_repair import parse_yaml
from .design_contract import strict_json

REVIEW_INSTRUCTION = """当前调用提供辅助审核意见，不生成或改写用例，也不决定生成是否成功。读取技能的缺口判断规则。
重点检查候选是否忠实实现已审核设计；发现上游设计矛盾时说明需人工确认设计，不重新裁决全部设计。
执行器支持环境变量引用和步骤成功后的 saveTo 提取；先核查先提取后引用及对象身份，不能将合法动态取值链路判为不可实现。
以原始功能用例、已审核设计、控件清单和源码为依据，逐条检查 missingFields，也检查是否通过删除标记隐藏未实现目标。
检查：字段实际用途与缺口一致；用户能在执行前提供该数据或补定位；本次操作产生的 ID/基线取值不能冒充静态输入；
已知值不应丢失；同一步同一原因不重复；行定位应保持唯一对象身份；定位缺失不等于能力缺失；
断言必须表达原预期，不能把比较清单/数量挂到空表可见性或等待毫秒值上。源码关系可用于实现断言，但不能改变业务预期。
有真实独立准备条件可以 fields=[]；同一数据出现在不同步骤是合法的。已有历史记录的已知 ID 是合法静态数据。
仅报告有具体证据的问题，不凭措辞或猜测否定标记。无法实现的已审核目标明确报告设计冲突，不能建议删掉目标通过校验。

能力判断须考虑定位器谓词，而非只看关键字名称：有源码 DOM 证据时，assert_visible 配合 XPath
表格[count(tbody/tr)=N] 可断言精确行数，复选框[@aria-checked='true'] 可断言选中态，
状态节点[normalize-space(.)='A' or normalize-space(.)='B'] 可保留 OR。只有谓词确实表达目标才算覆盖。
两个依次执行的断言是 AND，不能建议用它们表达 OR。可见第 N 行只证明至少 N 行。
否定型预期（元素或提示不应出现）由 assert_hidden 表达，需要唯一定位与毫秒超时；
超时值不是业务期望，不能把否定结论降级成同一操作的成功提示。
这些是实现策略示例，不是待复用的具体定位器；必须核查源码属性、表格范围、分页与虚拟滚动。
证据与修复建议分别验证：发现实现不符合需求时保留业务预期，建议修复定位/表达或明确待设计确认，
不得建议把需求改成源码默认行为；无法判断的 DOM 缺口可由用户补定位，只有明确证据才判不可补。
修复不得通过删除断言、改比对对象、缩窄期望或换成更弱条件通过。

区分取值时刻与值的来源：执行时读取一个已存在记录的 ID，并不代表该 ID 执行前不可提供；
bookkeeping 也不自动构成运行时能力缺口。只有本次动作新建、变化后才确定的值，或必须实时对照的基线，
才按 runtime_value 检查。可提前提供的既有清单应保留真实缺口，不能仅因前置条件未逐项列出就拒绝。
测试可以揭示当前实现的缺陷：保持原预期且定位有依据的断言，即使当前实现会失败，也不是生成错误。
源码未找到提示/控件本身不证明它不存在；缺少 DOM 证据时可标真实 locator 缺口并说明需用户确认。
只有缺口与字段/断言不对应、伪造已知节点或补值后仍不表达原目标时才拒绝，不能要求测试只断言当前行为。
严格返回 JSON 对象 {"issues": [...]}。每项只包含 caseIndex、stepIndex（均从1开始）、
code（runtime_value/unfillable_assertion/field_mismatch/duplicate_gap/identity/coverage）、evidence、repair。
evidence 说明候选具体内容与原始目标/源码的冲突，repair 说明保留目标的修正方向。无问题返回 {"issues": []}。
这是一份内部复核报告，不是生成产物；不返回 YAML、不添加用例字段、不修改任何输入文件。"""


def review_issues(raw: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    report = strict_json(raw)
    if not isinstance(report, dict) or set(report) != {"issues"}:
        raise ValueError("复核报告必须只有 issues 数组")
    issues = report["issues"]
    if not isinstance(issues, list):
        raise ValueError("issues 必须为数组")
    for index, issue in enumerate(issues, 1):
        if not isinstance(issue, dict) or set(issue) != {
            "caseIndex",
            "stepIndex",
            "code",
            "evidence",
            "repair",
        }:
            raise ValueError("复核问题字段不完整")
        case, step = issue["caseIndex"], issue["stepIndex"]
        if type(case) is not int or not 1 <= case <= len(rows):
            raise ValueError(f"issues[{index}].caseIndex 必须为 1..{len(rows)} 的候选用例编号")
        if type(step) is not int or not 1 <= step <= len(rows[case - 1]["stepsJson"]):
            raise ValueError(
                f"issues[{index}].stepIndex: 候选用例 {case} 仅有 "
                f"{len(rows[case - 1]['stepsJson'])} 步；按 candidateYaml 的步骤内容和 "
                "orderNo 定位，不使用原始设计的 sourceStepNo。保留问题证据，修正引用位置。"
            )
        if not isinstance(issue["code"], str) or issue["code"] not in {
            "runtime_value",
            "unfillable_assertion",
            "field_mismatch",
            "duplicate_gap",
            "identity",
            "coverage",
        }:
            raise ValueError("未知复核问题类型")
        if any(
            not isinstance(issue[k], str) or not issue[k].strip() for k in ("evidence", "repair")
        ):
            raise ValueError("复核问题必须包含证据和修正方向")
    return issues


REVIEW_TIMEOUT_SECONDS = 120
logger = logging.getLogger(__name__)


class SemanticReview(TypedDict):
    """Advisory outcome; incomplete never means an empty successful review."""

    status: Literal["completed", "incomplete"]
    issues: list[dict[str, Any]]
    errorCode: str


async def check_missing_semantics(
    *,
    raw: str,
    inputs: dict[str, Any],
    generate: Callable,
    diagnostic_dir: Path,
) -> SemanticReview:
    rows = parse_yaml(raw)
    payload = {k: v for k, v in inputs.items() if k != "currentArtifact"}
    payload["candidateYaml"] = raw
    original = json.dumps(payload, ensure_ascii=False)
    prompt = original
    diagnostic_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    phase = "model_error"
    try:
        async with asyncio.timeout(REVIEW_TIMEOUT_SECONDS):
            # A malformed report may be repaired once, never the candidate YAML.
            for attempt in range(2):
                phase = "model_error"
                response = generate(prompt, REVIEW_INSTRUCTION)
                if inspect.isawaitable(response):
                    response = await response
                if getattr(response, "error", None):
                    return SemanticReview(status="incomplete", issues=[], errorCode="model_error")
                text = response if isinstance(response, str) else getattr(response, "content", None)
                reason = getattr(response, "finish_reason", None) or getattr(
                    response, "stop_reason", None
                )
                metadata = getattr(response, "metadata", None)
                if reason is None and isinstance(metadata, dict):
                    reason = metadata.get("finish_reason")
                if reason in {"length", "max_tokens", "max_output_tokens"}:
                    return SemanticReview(status="incomplete", issues=[], errorCode="truncated")
                phase = "invalid_report"
                error = None
                issues = []
                try:
                    if not isinstance(text, str):
                        raise ValueError("复核报告必须为文本")
                    issues = review_issues(text, rows)
                except ValueError as exc:
                    error = str(exc)
                path = diagnostic_dir / f"attempt-{attempt}.json"
                with path.open("w", encoding="utf-8") as output:
                    path.chmod(0o600)
                    json.dump({"rawResponse": text, "error": error}, output, ensure_ascii=False)
                if error is None:
                    return SemanticReview(status="completed", issues=issues, errorCode="")
                prompt = (
                    original
                    + "\n上一次复核报告：\n"
                    + str(text)
                    + "\n报告格式问题：\n"
                    + error
                    + "\n只修复报告 JSON 和引用位置，保留证据；不要修改候选 YAML。"
                )
    except TimeoutError:
        return SemanticReview(status="incomplete", issues=[], errorCode="timeout")
    except PermissionError:
        raise
    except Exception as exc:
        # Do not log provider exception text, prompts, output or credentials.
        logger.warning(
            "UI advisory review incomplete batch=%s error_type=%s stack=%s",
            inputs.get("batch", {}).get("index"),
            type(exc).__name__,
            "".join(traceback.format_tb(exc.__traceback__)),
        )
        return SemanticReview(status="incomplete", issues=[], errorCode=phase)
    return SemanticReview(status="incomplete", issues=[], errorCode="invalid_report")
