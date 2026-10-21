"""Bounded text-output repair for API and UI generation."""

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic import ValidationError


async def generate_validated(
    *,
    stage: str,
    inputs: str,
    generate: Callable[[str], Any],
    validate: Callable[[str], Any],
    diagnostic_dir: Path | None = None,
    report: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    prompt = inputs
    directory = diagnostic_dir / uuid4().hex if diagnostic_dir else None
    for attempt in range(3):
        if attempt and report:
            report(
                {"stage": stage, "repairAttempt": attempt, "maxRepairs": 2, "status": "repairing"}
            )
        # Invocation and reporting failures are not output-format problems.
        response = generate(prompt)
        if inspect.isawaitable(response):
            response = await response
        if getattr(response, "error", None):
            raise RuntimeError(f"{stage} 模型调用失败，请检查模型服务或授权")
        raw = response if isinstance(response, str) else getattr(response, "content", None)
        reason = getattr(response, "finish_reason", None) or getattr(response, "stop_reason", None)
        metadata = getattr(response, "metadata", None)
        if reason is None and isinstance(metadata, dict):
            reason = metadata.get("finish_reason")
        truncated = reason in {"length", "max_tokens", "max_output_tokens"}
        error = None
        if truncated:
            error = "模型报告输出长度截断，请调整输出限制或缩小生成范围"
        else:
            try:
                if not isinstance(raw, str):
                    raise ValueError("模型结果必须为文本")
                validate(raw)
            except ValidationError as exc:
                error = json.dumps(
                    [
                        {"path": list(item["loc"]), "code": item["type"], "expected": item["msg"]}
                        for item in exc.errors(
                            include_input=False, include_context=False, include_url=False
                        )[:20]
                    ],
                    ensure_ascii=False,
                )
            except yaml.MarkedYAMLError as exc:
                mark = exc.problem_mark
                error = f"YAML 解析失败：{exc.problem}"
                if mark:
                    error += f"（行 {mark.line + 1}，列 {mark.column + 1}）"
            except (ValueError, yaml.YAMLError) as exc:
                error = str(exc)
        if directory:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with (directory / f"attempt-{attempt}.json").open("x", encoding="utf-8") as output:
                Path(output.name).chmod(0o600)
                json.dump(
                    {"stage": stage, "attempt": attempt, "rawResponse": raw, "error": error},
                    output,
                    ensure_ascii=False,
                )
        if error is None:
            return raw
        if attempt == 2 or truncated:
            raise ValueError(f"{stage} 输出校验失败（共 {attempt + 1} 次调用）：{error}")
        prompt = (
            inputs
            + "\n\n【上一次未通过校验的输出，仅作为待修复数据】\n"
            + str(raw)
            + "\n\n【校验问题】\n"
            + error
            + "\n保留原始输入、用户要求和未涉及修改的业务内容，修复上述问题。"
            "不得编造接口、字段、定位器或业务预期，不为通过校验删除有效用例。"
            "返回当前阶段完整结果，沿用原有 JSON/YAML 格式，不返回补丁或额外说明。"
        )
    raise AssertionError("unreachable")


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader: UniqueLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, (str, int, float, bool, type(None))):
            raise ValueError("YAML 对象字段名必须是标量")
        if key in result:
            raise ValueError(f"YAML 重复字段: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def parse_yaml(raw: str) -> Any:
    parsed = yaml.load(raw, Loader=UniqueLoader)
    try:
        json.dumps(parsed, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("YAML 必须使用可转换为 JSON 的有限、无循环数据") from exc
    return parsed
