"""Check generated test points against their full inputs before exposing the candidate."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from .validation import OutputValidationError, generate_validated

AUDIT_CONDITIONS = """只核对测试点中的必要条件及预期是否有依据，不检查拆分或遗漏。逐条将对象、条件和结果
与完整需求对照；条件 A 与 B 同时满足时可得结果 R，并不能推出不满足 B 时一定没有 R。若需求说某条件下
“不保证 R”，这一说法不是“不发生 R”的确认，也不是可以判定的预期。操作结果本身也可能是必要条件：例如材料只规定
“重试成功后生成产物”，不能把预期扩大为“重试时生成产物”，因为重试仍可能失败。只列出缺失必要条件、额外限定范围或预期
缺乏依据的名称；判定前核对全部适用规则。允许结合多条已确认规则推导：若明确不短于阈值的对象生成产物，
而小于阈值丢弃，等于阈值符合前者，不能只因未逐条列出而否定。功能可独立交付不等于另一个功能在任意开关状态
下均不受影响。不要因检查方法未知否定已确定结果。"""

AUDIT_COVERAGE = """只核对测试点的覆盖和拆分，不生成测试点。检查可分别失败的独立判断是否合并、有依据的独立要求
或分支是否遗漏；比较对象、条件、触发与结果，识别没有独立验收价值的重复目标。已由具体场景完整覆盖且无额外
判断的笼统点不另保留，不能将不同结果合并。入口位置与文案、阻断与提示、产物内容与关联对象均可能独立失败；
有明确要求时分别核对，但纯内部实现及执行路径不自动构成独立验收目标。统一提示及其内容仍是一个目标，明确的
一组产物关系不按名词数量机械拆分。明确要求的先后顺序是独立关系：分别验证两个结果不能证明顺序正确，缺少观察
手段不能据此删除有依据的顺序目标。只将预期已明确或可由完整规则推导的分支视为遗漏；“开启不保证生成”不等于
“条件不满足时不生成”，也不能要求以“不保证生成”作为验收结果。结果未确定的分支留待确认，不作为漏项补入。"""

AUDIT_OUTPUT = """遵循用户最新修订指令及明确排除范围，不恢复用户明确删除的条目。只返回 JSON 对象
{"issues":[...]}；每项 case_name 填原测试点名称，遗漏目标填 null，problem 说明具体问题及依据。无问题时返回
{"issues":[]}。不要编造问题。"""

MAX_CORRECTIONS = 3
CONDITION_BATCH_SIZE = 10


async def generate_reviewed_points(
    *,
    generation_input: str,
    evidence_input: str,
    user_instruction: str,
    generate: Callable[[str, str], Awaitable[Any]],
) -> str:
    """Generate, independently audit, and correct a candidate before it is exposed."""
    draft = await generate_validated(
        stage="case_names",
        inputs=generation_input,
        generate=lambda prompt: generate(prompt, "generate"),
    )
    for round_no in range(MAX_CORRECTIONS + 1):
        points = [
            point["case_name"]
            for category in json.loads(draft)["categories"]
            for dimension in category["data"]
            for point in dimension["test_points"]
        ]
        batches = [
            points[i : i + CONDITION_BATCH_SIZE]
            for i in range(0, len(points), CONDITION_BATCH_SIZE)
        ] or [[]]
        audit_slots = asyncio.Semaphore(2)

        async def audit_batch(instruction: str, candidate: str, phase: str) -> str:
            async with audit_slots:
                return await generate_validated(
                    stage="case_names_audit",
                    inputs="\n\n".join(
                        [
                            instruction,
                            AUDIT_OUTPUT,
                            "【原始需求、分析与本轮修订】\n" + evidence_input,
                            "【额外用户要求】\n" + user_instruction,
                            "【待核对测试点】\n" + candidate,
                        ]
                    ),
                    generate=lambda prompt: generate(prompt, phase),
                )

        audits = await asyncio.gather(
            *(
                audit_batch(
                    AUDIT_CONDITIONS,
                    json.dumps(batch, ensure_ascii=False),
                    f"audit-conditions-{round_no}" + (f"-batch-{i}" if len(batches) > 1 else ""),
                )
                for i, batch in enumerate(batches)
            )
        )
        issues = [issue for audit in audits for issue in json.loads(audit)["issues"]]
        if not issues:
            audit = await audit_batch(AUDIT_COVERAGE, draft, f"audit-coverage-{round_no}")
            issues = json.loads(audit)["issues"]
        audit = json.dumps({"issues": issues}, ensure_ascii=False)
        draft_names = set(points)
        if any(
            issue["case_name"] is not None and issue["case_name"] not in draft_names
            for issue in issues
        ):
            raise OutputValidationError("测试点复核引用了不存在的测试点，无法应用复核结果")
        if not issues:
            return draft
        if round_no == MAX_CORRECTIONS:
            raise OutputValidationError(
                f"测试点经 {MAX_CORRECTIONS} 次修订后仍未通过依据与覆盖复核（{len(issues)} 项问题）"
            )
        correction_input = "\n\n".join(
            [
                generation_input,
                "【待复核的测试点】\n" + draft,
                "【逐条复核问题】\n" + audit,
                "请依据原始材料和用户最新要求逐项核对复核问题，修正有依据的问题，"
                "保留其余已确认目标及其完整条件；拆分或改写时不得丢失原有必要条件，"
                "并重新核对改写后的每个结果是否仍满足全部适用条件；只输出完整修订后的测试点 JSON。",
            ]
        )
        draft = await generate_validated(
            stage="case_names",
            inputs=correction_input,
            generate=lambda prompt: generate(prompt, f"correct-{round_no}"),
        )
    raise AssertionError("unreachable")
