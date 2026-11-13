"""Bounded format repair shared by every functional generation path."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore
from uuid import uuid4

from pydantic import ValidationError

from testing_agent_ai_worker.traceable_test_points import (
    _validator as traceable_validator,
)
from testing_agent_ai_worker.traceable_test_points import (
    validate_traceable_test_points,
)

from .contracts import CONTRACTS, DetailedCasesOutput

CLARIFICATION_PREFIX = "CLARIFICATION_REQUIRED:"


@dataclass
class ValidationContext:
    diagnostic_dir: Path
    report: Callable[[dict], None | Awaitable[None]]
    task_id: str = ""
    run_id: str = ""
    review_concurrency: int = 4
    review_limiter: BoundedSemaphore | None = None


context: ContextVar[ValidationContext | None] = ContextVar("functional_validation", default=None)


class OutputValidationError(ValueError):
    pass


def normalize_json(raw: str) -> str:
    text = raw.strip()
    match = re.fullmatch(r"```(?:json)?\s*\n(.*)\n```", text, re.DOTALL)
    return match.group(1).strip() if match else text


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"non-standard JSON value: {value}")


def validate_output(
    stage: str, raw: str, previous_cases=(), expected_case_ids=None, material=None, analysis=None
):
    parsed = json.loads(normalize_json(raw), object_pairs_hook=_pairs, parse_constant=_constant)
    if stage == "traceable_case_names":
        validate_traceable_test_points(parsed, material, analysis)
        return json.dumps(parsed, ensure_ascii=False)
    model = CONTRACTS[stage].model_validate(parsed)
    if stage == "requirement_analysis" and material is not None:
        blocks = {item["id"] for item in material.get("materialBlocks", [])}
        questions = {item["id"] for item in material.get("questions", [])}
        for group in (model.testObjects, model.impactAreas, model.risks, model.openQuestions):
            for entry in group:
                if not set(entry.sourceBlockIds) <= blocks:
                    raise ValueError(f"{entry.id}: unknown material block ID")
                if not set(getattr(entry, "sourceQuestionIds", [])) <= questions:
                    raise ValueError(f"{entry.id}: unknown source question ID")
    if stage == "detailed_cases" and previous_cases:
        DetailedCasesOutput.model_validate(
            {"cases": [*previous_cases, *model.model_dump()["cases"]]}
        )
    if stage == "relation_analysis" and expected_case_ids is not None:
        referenced = {
            *(case_id for path in model.main_paths for case_id in path.case_ids),
            *(edge.from_case_id for edge in model.edges),
            *(edge.to_case_id for edge in model.edges),
        }
        unknown = referenced - set(expected_case_ids)
        if unknown:
            raise ValueError(
                "所有引用的 case_id 必须逐字存在于输入用例集合，未知 ID："
                + ", ".join(sorted(unknown))
            )
    return model.model_dump_json(by_alias=True)


def issues_for(exc):
    if isinstance(exc, ValidationError):
        return [
            {
                "path": "$"
                + "".join(
                    f"[{part}]" if isinstance(part, int) else f".{part}" for part in e["loc"]
                ),
                "code": e["type"],
                "expected": e["msg"],
                "actual": repr(e.get("input"))[:200],
            }
            for e in exc.errors(include_url=False, include_context=False)
        ]
    return [{"path": "$", "code": "invalid_json", "expected": str(exc), "actual": ""}]


async def generate_validated(
    *,
    stage,
    inputs,
    generate,
    previous_cases=(),
    module="",
    batch=0,
    expected_case_ids=None,
    material=None,
    analysis=None,
    initial_response: str | None = None,
    post_validate: Callable[[dict], None] | None = None,
):
    """Return canonical JSON, or raise without publishing any invalid artifact."""
    schema_data = (
        traceable_validator().schema
        if stage == "traceable_case_names"
        else CONTRACTS[stage].model_json_schema(by_alias=True)
    )
    schema = json.dumps(schema_data, ensure_ascii=False)
    original = inputs + "\n\n【输出 JSON Schema】\n" + schema
    prompt = original
    ctx = context.get()
    call_id = uuid4().hex
    for attempt in range(3):
        if ctx:
            event = {
                "stage": stage,
                "module": module,
                "batch": batch,
                "repairAttempt": attempt,
                "maxRepairs": 2,
                "status": "repairing" if attempt else "generating",
            }
            if inspect.iscoroutinefunction(ctx.report):
                await ctx.report(event)
            else:
                reported = await asyncio.to_thread(ctx.report, event)
                if inspect.isawaitable(reported):
                    await reported
        # Transport/auth failures intentionally bypass format repair.
        response = (
            initial_response
            if attempt == 0 and initial_response is not None
            else await generate(prompt)
        )
        if getattr(response, "error", None):
            raise RuntimeError(f"模型调用失败：{response.error}")
        raw = response if isinstance(response, str) else response.content
        reason = getattr(response, "finish_reason", None) or getattr(response, "stop_reason", None)
        metadata = getattr(response, "metadata", None)
        if reason is None and isinstance(metadata, dict):
            reason = metadata.get("finish_reason")
        errors = []
        normalized = None
        if reason in {"length", "max_tokens", "max_output_tokens"}:
            errors = [
                {
                    "path": "$",
                    "code": "output_truncated",
                    "expected": "完整输出；模型报告长度截断",
                    "actual": str(reason),
                }
            ]
        elif (
            stage == "detailed_cases"
            and isinstance(raw, str)
            and raw.strip().startswith(CLARIFICATION_PREFIX)
        ):
            errors = [
                {
                    "path": "$",
                    "code": "clarification_required",
                    "expected": raw.strip()[len(CLARIFICATION_PREFIX) :].strip(),
                    "actual": "",
                }
            ]
        else:
            try:
                normalized = validate_output(
                    stage,
                    raw,
                    previous_cases,
                    expected_case_ids=expected_case_ids,
                    material=material,
                    analysis=analysis,
                )
                if post_validate is not None:
                    post_validate(json.loads(normalized))
            except (ValueError, TypeError) as exc:
                normalized = None
                errors = issues_for(exc)
        if ctx:
            directory = ctx.diagnostic_dir / stage / f"batch-{batch}-{call_id}"
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            target = directory / f"attempt-{attempt}.json"
            # No prompts, model connection settings or credentials are recorded.
            with target.open("x", encoding="utf-8") as fh:
                target.chmod(0o600)
                json.dump(
                    {
                        "stage": stage,
                        "module": module,
                        "batch": batch,
                        "attempt": attempt,
                        "rawResponse": raw,
                        "errors": errors,
                    },
                    fh,
                    ensure_ascii=False,
                    indent=2,
                )
        if normalized is not None:
            return normalized
        if errors[0]["code"] == "clarification_required":
            raise OutputValidationError(
                "完整用例生成需要补充信息"
                + (f"（{module}）" if module else "")
                + "：\n"
                + (errors[0]["expected"] or "请补充影响执行或判定的业务依据")
            )
        if attempt == 2 or errors[0]["code"] == "output_truncated":
            raise OutputValidationError(
                f"{stage}{('/' + module) if module else ''} 输出校验失败（共 {attempt + 1} 次调用）："
                + json.dumps(errors[:20], ensure_ascii=False)
            )
        prompt = (
            original
            + "\n\n【上一次未通过校验的输出，仅作为待修复数据】\n"
            + str(raw)
            + "\n\n【校验问题，最多列出20项】\n"
            + json.dumps(errors[:20], ensure_ascii=False)
            + "\n请保留原有业务含义和未涉及修改的内容，修复上述问题。"
            "返回本阶段完整 JSON，不要只返回修改片段，不附加说明。"
        )
