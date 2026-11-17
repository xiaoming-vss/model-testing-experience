"""Compile a run specification into the fixed k6 template's plan."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts.spec import (
    ArrivalRateLoad,
    ContentType,
    LoadSpec,
    RemoteWriteSpec,
    RequestRateLoad,
    RunSpec,
    StepSpec,
    VusLoad,
)
from ..core.config import Settings
from ..core.errors import CompileError
from ..core.io import write_secure_bytes, write_secure_text
from .data import Dataset, load_datasets, write_datasets

PLAN_VERSION = "1.0"
TEMPLATE_VERSION = "1.0.0"

_TEMPLATE_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_BUILTINS = frozenset({"uuid", "timestamp", "iteration", "vu"})


@dataclass(frozen=True)
class CompiledPlan:
    run_id: str
    plan_path: Path
    script_path: Path
    plan: dict[str, Any]
    env_values: dict[str, str]
    remote_write: RemoteWriteSpec
    max_duration_seconds: int
    stop_grace_seconds: int
    template_version: str
    script_sha256: str


def compile_run_spec(
    spec: RunSpec,
    spec_dir: Path,
    output_dir: Path,
    settings: Settings,
) -> CompiledPlan:
    datasets = load_datasets(spec.case.data, spec_dir, settings.runner.max_data_file_mb)
    _validate_data_columns(datasets)

    data_columns = {column for dataset in datasets for column in dataset.columns}
    known_vars: set[str] = set()
    env_refs: set[str] = set()
    steps: list[dict[str, Any]] = []

    for step in spec.case.steps:
        _validate_step(step)
        _check_value(
            step.path,
            step_name=step.name,
            known_vars=known_vars,
            data_columns=data_columns,
            env_names=set(spec.environment.variables),
            env_refs=env_refs,
        )
        for header_name, header_value in step.headers.items():
            if "{{" in header_name:
                raise CompileError(f"步骤 {step.name} 的请求头名称不支持模板占位符")
            _check_value(
                header_value,
                step_name=step.name,
                known_vars=known_vars,
                data_columns=data_columns,
                env_names=set(spec.environment.variables),
                env_refs=env_refs,
            )
        _check_value(
            step.body,
            step_name=step.name,
            known_vars=known_vars,
            data_columns=data_columns,
            env_names=set(spec.environment.variables),
            env_refs=env_refs,
        )
        for check in step.checks:
            _check_value(
                check.value,
                step_name=step.name,
                known_vars=known_vars,
                data_columns=data_columns,
                env_names=set(spec.environment.variables),
                env_refs=env_refs,
            )

        steps.append(step.model_dump(mode="json", by_alias=True))
        for rule in step.extract:
            known_vars.add(rule.name)

    env_values = {name: spec.environment.variables[name] for name in sorted(env_refs)}
    options = _build_options(spec, spec.limits.stop_grace_seconds)
    plan: dict[str, Any] = {
        "planVersion": PLAN_VERSION,
        "runId": spec.run_id,
        "baseUrl": spec.environment.base_url,
        "options": options,
        "steps": steps,
        "data": [
            {
                "name": dataset.name,
                "strategy": dataset.strategy.value,
                "onExhausted": dataset.on_exhausted.value,
                "rowCount": len(dataset.rows),
                "columns": list(dataset.columns),
            }
            for dataset in datasets
        ],
        "envKeys": sorted(env_refs),
        "templateVersion": TEMPLATE_VERSION,
    }

    template_bytes = _template_path().read_bytes()
    script_sha256 = hashlib.sha256(template_bytes).hexdigest()
    write_secure_bytes(output_dir / "main.js", template_bytes)
    write_secure_text(
        output_dir / "plan.json",
        json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
    )
    write_datasets(datasets, output_dir / "data")

    max_duration = spec.limits.max_duration_seconds
    if settings.runner.max_duration_seconds > 0:
        max_duration = min(max_duration, settings.runner.max_duration_seconds)
    stop_grace = spec.limits.stop_grace_seconds
    if settings.runner.stop_grace_seconds > 0:
        stop_grace = min(stop_grace, settings.runner.stop_grace_seconds)

    return CompiledPlan(
        run_id=spec.run_id,
        plan_path=output_dir / "plan.json",
        script_path=output_dir / "main.js",
        plan=plan,
        env_values=env_values,
        remote_write=spec.remote_write,
        max_duration_seconds=max_duration,
        stop_grace_seconds=stop_grace,
        template_version=TEMPLATE_VERSION,
        script_sha256=script_sha256,
    )


def _validate_data_columns(datasets: list[Dataset]) -> None:
    seen: dict[str, str] = {}
    for dataset in datasets:
        for column in dataset.columns:
            if column in seen:
                raise CompileError(f"数据列 {column} 在 {seen[column]} 和 {dataset.name} 中重复")
            seen[column] = dataset.name


def _validate_step(step: StepSpec) -> None:
    if not (
        step.path.startswith("/")
        or step.path.startswith("http://")
        or step.path.startswith("https://")
    ):
        raise CompileError(f"步骤 {step.name} 的 path 必须以 / 或 http(s):// 开头")
    if step.content_type is ContentType.NONE and step.body is not None:
        raise CompileError(f"步骤 {step.name} 的 contentType=none 时不能提供 body")
    if step.content_type is ContentType.FORM and step.body is not None:
        if not isinstance(step.body, dict):
            raise CompileError(f"步骤 {step.name} 的 contentType=form 时 body 必须是对象")
    if step.content_type is ContentType.TEXT and step.body is not None:
        if not isinstance(step.body, str):
            raise CompileError(f"步骤 {step.name} 的 contentType=text 时 body 必须是字符串")


def _check_value(
    value: Any,
    *,
    step_name: str,
    known_vars: set[str],
    data_columns: set[str],
    env_names: set[str],
    env_refs: set[str],
) -> None:
    if isinstance(value, str):
        for match in _TEMPLATE_RE.finditer(value):
            expression = match.group(1).strip()
            if not expression:
                raise CompileError(f"步骤 {step_name} 存在空的模板占位符")
            if expression in _BUILTINS:
                continue
            if expression.startswith("data."):
                column = expression[5:]
                if column not in data_columns:
                    raise CompileError(f"步骤 {step_name} 引用了不存在的数据列: {column}")
            elif expression.startswith("var."):
                name = expression[4:]
                if name not in known_vars:
                    raise CompileError(f"步骤 {step_name} 引用了尚未提取的变量: {name}")
            elif expression.startswith("env."):
                name = expression[4:]
                if name not in env_names:
                    raise CompileError(f"步骤 {step_name} 引用了不存在的环境变量: {name}")
                env_refs.add(name)
            else:
                raise CompileError(f"步骤 {step_name} 存在未知模板占位符: {expression}")
        return

    if isinstance(value, list):
        for item in value:
            _check_value(
                item,
                step_name=step_name,
                known_vars=known_vars,
                data_columns=data_columns,
                env_names=env_names,
                env_refs=env_refs,
            )
        return

    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CompileError(f"步骤 {step_name} 的对象键必须是字符串")
            if "{{" in key:
                raise CompileError(f"步骤 {step_name} 的对象键不支持模板占位符: {key}")
            _check_value(
                item,
                step_name=step_name,
                known_vars=known_vars,
                data_columns=data_columns,
                env_names=env_names,
                env_refs=env_refs,
            )


def _build_options(spec: RunSpec, stop_grace_seconds: int) -> dict[str, Any]:
    scenario = _build_scenario(spec.case.load, stop_grace_seconds)
    options: dict[str, Any] = {
        "scenarios": {"main": scenario},
        "tags": {"run_id": spec.run_id},
    }
    if spec.case.acceptance.criteria:
        options["thresholds"] = {
            metric: list(expressions)
            for metric, expressions in spec.case.acceptance.criteria.items()
        }
    return options


def _build_scenario(load: LoadSpec, stop_grace_seconds: int) -> dict[str, Any]:
    graceful_stop = f"{stop_grace_seconds}s"
    if isinstance(load, VusLoad):
        if load.ramp_up:
            return {
                "executor": "ramping-vus",
                "startVUs": 0,
                "stages": [
                    {"duration": load.ramp_up, "target": load.vus},
                    {"duration": load.duration, "target": load.vus},
                    {"duration": load.ramp_down, "target": 0},
                ],
                "gracefulStop": graceful_stop,
            }
        return {
            "executor": "constant-vus",
            "vus": load.vus,
            "duration": load.duration,
            "gracefulStop": graceful_stop,
        }
    if isinstance(load, ArrivalRateLoad):
        return {
            "executor": "constant-arrival-rate",
            "rate": load.rate,
            "timeUnit": load.time_unit,
            "duration": load.duration,
            "preAllocatedVUs": load.pre_allocated_vus,
            "maxVUs": load.max_vus,
            "gracefulStop": graceful_stop,
        }
    if isinstance(load, RequestRateLoad):
        return {
            "executor": "constant-arrival-rate",
            "rate": load.rate,
            "timeUnit": load.time_unit,
            "duration": load.duration,
            "preAllocatedVUs": load.pre_allocated_vus,
            "maxVUs": load.max_vus,
            "gracefulStop": graceful_stop,
        }
    raise CompileError("未知负载模型")


def _template_path() -> Path:
    return Path(__file__).resolve().parent / "templates" / "main.js"
