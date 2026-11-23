"""Assemble the local once-mode execution chain."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from .compiler.compiler import CompiledPlan, compile_run_spec
from .contracts.result import (
    ResultFlag,
    RunnerInfo,
    RunOutcome,
    RunResult,
    RunStatus,
)
from .contracts.spec import RunSpec, load_run_spec
from .core.config import Settings
from .runner.k6 import K6Execution, K6Runner
from .runner.workspace import Workspace


async def run_once(settings: Settings, spec_path: Path) -> RunResult:
    """Load one run spec, compile it, execute k6 and write ``result.json``."""

    spec = load_run_spec(spec_path)
    spec_dir = spec_path.resolve().parent
    workspace = Workspace.create(Path(settings.runner.workspace_root), spec.run_id)
    compiled = compile_run_spec(spec, spec_dir, workspace.root, settings)
    execution = await K6Runner(settings).run(compiled, workspace)
    result = build_result(spec, compiled, execution)
    workspace.write_result(result.model_dump_json(by_alias=True, indent=2))
    return result


def build_result(spec: RunSpec, compiled: CompiledPlan, execution: K6Execution) -> RunResult:
    status, outcome, error_message = _classify(execution, bool(spec.case.acceptance.criteria))
    flags: list[ResultFlag] = []
    if execution.summary_missing:
        flags.append(ResultFlag.SUMMARY_MISSING)
    if execution.log_truncated:
        flags.append(ResultFlag.LOG_TRUNCATED)
    if execution.remote_write_error:
        flags.append(ResultFlag.REMOTE_WRITE_ERROR)

    return RunResult(
        run_id=spec.run_id,
        status=status,
        outcome=outcome,
        exit_code=execution.exit_code,
        started_at=execution.started_at.isoformat(),
        finished_at=execution.finished_at.isoformat(),
        duration_ms=execution.duration_ms,
        k6_version=execution.k6_version,
        template_version=compiled.template_version,
        script_sha256=compiled.script_sha256,
        summary=execution.summary,
        flags=flags,
        error_message=error_message,
        log_tail=execution.log_tail,
        runner=RunnerInfo(
            hostname=socket.gethostname(),
            cpu_count=os.cpu_count() or 1,
            k6_version=execution.k6_version,
        ),
    )


def _classify(execution: K6Execution, has_criteria: bool) -> tuple[RunStatus, RunOutcome, str]:
    if execution.timed_out:
        return (
            RunStatus.FAILED,
            RunOutcome.EXECUTION_ERROR,
            execution.error_message or "执行超时",
        )
    if execution.stopped:
        return RunStatus.STOPPED, RunOutcome.STOPPED, execution.error_message
    if execution.exit_code == 0:
        outcome = RunOutcome.PASSED if has_criteria else RunOutcome.INCONCLUSIVE
        return RunStatus.COMPLETED, outcome, ""
    if execution.exit_code == 99:
        return RunStatus.COMPLETED, RunOutcome.THRESHOLD_FAILED, ""
    return (
        RunStatus.FAILED,
        RunOutcome.EXECUTION_ERROR,
        execution.error_message or f"k6 退出码 {execution.exit_code}",
    )
