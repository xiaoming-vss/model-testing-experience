"""UI test case generation executor."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from testing_agent_ai_worker.agent.config_builder import task_config_path
from testing_agent_ai_worker.agent.paths import (
    resolve_runtime_paths,
    resolve_task_workspace,
)
from testing_agent_ai_worker.agent.skill_step import run_skill_step
from testing_agent_ai_worker.config.models import AgentBackendConfig
from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.tasks.output_repair import generate_validated, parse_yaml
from testing_agent_ai_worker.tasks.result_summary import build_task_result_summary
from testing_agent_ai_worker.tasks.ui_case_generate.missing_fields import draft_step_for_validation
from testing_agent_ai_worker.tasks.ui_case_generate.source_archive import SourceArchiveDownloader
from testing_agent_ai_worker.worker.runner import TaskExecutor

from .ui_step_extract import normalize_save_to
from .ui_variable_template import TOKEN_PATTERN, validate_step_variables

UI_CASE_SKILL_NAME = "generate-ui-test-case"
UI_CASE_YAML_ONLY_INSTRUCTION = """请分析指定的前端源码目录并生成 UI 自动化测试用例。
源码根目录：{source_root}
始终返回 YAML list，即使只有一条用例。每条用例必须包含 name、enabled、stepsJson、orderNo；每个步骤必须包含 orderNo、stepName、keyword、continueOnFailure、enabled。operationValue、locatorType、locatorValue、comparator 必须严格按照 keyword 规则提供。缺失内容保留步骤并使用 missingFields 数组：每项含 fields、operation、target、value、reason，fields列出的字段显式为null，其他已知字段保留。前置准备缺口使用空fields。不要返回阻塞字符串。全部目标明确排除时可返回空列表[]。不要输出 Markdown 代码块、解释文字或 JSON。"""


UI_STAGE_YAML_INSTRUCTION = """直接返回平台原格式的 YAML 用例列表。
每条用例仅包含 name、enabled、orderNo、stepsJson；每步包含 orderNo、stepName、keyword、continueOnFailure、enabled 及操作需要的字段。
支持 locatorValue/operationValue 中的环境变量和步骤成功后的 saveTo 提取；按平台协议填写，不以未知静态数据替代可提取的运行时值。
未知字段通过步骤内 missingFields 标记，每项包含 fields、operation、target、value、reason；缺失字段显式为 null，已知内容直接填写。
同一步中同一根因的缺口合并为一项。仅缺记录ID时保留已知定位类型，在reason中说明缺少数据及已知行定位规则，不重复声明缺少控件或再追加准备提醒。
无法操作或断言的目标由第二阶段筛选；保留已审核的可实现业务目标，不以人工确认替代断言。
不输出 draftVersion、dataRequirements、dataBindings、designConflicts、sourceRefs、purpose 或新变量协议。
"""


VALID_UI_LOCATOR_TYPES = {
    "css",
    "xpath",
    "text",
    "placeholder",
    "label",
    "test_id",
    "testid",
    "role",
}
VALID_UI_COMPARATORS = {"eq", "contains"}


@dataclass(frozen=True, slots=True)
class UiKeywordRule:
    locator_required: bool
    operation: str = "optional"
    comparator_required: bool = False


UI_KEYWORD_RULES = {
    "open": UiKeywordRule(False, "required"),
    "reload": UiKeywordRule(False),
    "click": UiKeywordRule(True),
    "dblclick": UiKeywordRule(True),
    "input": UiKeywordRule(True, "required"),
    "clear": UiKeywordRule(True, "forbidden"),
    "press": UiKeywordRule(True, "required"),
    "wait_text": UiKeywordRule(True, "required"),
    "assert_text": UiKeywordRule(True, "required", True),
    "assert_visible": UiKeywordRule(True, "required"),
    "assert_hidden": UiKeywordRule(True, "required"),
    "assert_url": UiKeywordRule(False, "required", True),
    "screenshot": UiKeywordRule(False, "forbidden"),
    "sleep": UiKeywordRule(False, "required"),
}


class UiCaseExecutor(TaskExecutor):
    """下载前端源码归档并调用 UI 用例生成技能。"""

    def __init__(
        self,
        *,
        agent_config: AgentBackendConfig,
        source_downloader: SourceArchiveDownloader,
        skill_runner=run_skill_step,
        skill_name: str = UI_CASE_SKILL_NAME,
    ) -> None:
        self.agent_config = agent_config
        self.runtime_paths = resolve_runtime_paths(agent_config)
        self.source_downloader = source_downloader
        self.skill_runner = skill_runner
        self.skill_name = skill_name

    def execute(self, task: Task, started_at: datetime, progress_callback) -> TaskResult | None:
        if task.task_type != "ui_case_generate":
            return self._failure(task, started_at, f"不支持的任务类型: {task.task_type}")

        try:
            workspace = resolve_task_workspace(self.agent_config, task)
            source_root = self.source_downloader.download_and_extract(
                source_archive_download_url=task.payload.source_archive_download_url,
                task=task,
                workspace=workspace,
            )
            if task.payload.metadata.get("uiWorkflowVersion") == "ui_three_stage/1.0":
                from testing_agent_ai_worker.tasks.ui_case_generate.chain import execute_stage

                with task_config_path(agent_config=self.agent_config, task=task) as config_path:
                    return execute_stage(
                        task=task,
                        started_at=started_at,
                        progress_callback=progress_callback,
                        source_root=source_root,
                        workspace=workspace,
                        config_path=config_path,
                        skill_runner=self.skill_runner,
                        validate_yaml=_validate_ui_stage_yaml,
                        yaml_instruction=UI_STAGE_YAML_INSTRUCTION,
                    )
            input_text = UI_CASE_YAML_ONLY_INSTRUCTION.format(source_root=source_root)
            if task.payload.extra_instruction.strip():
                input_text = f"{input_text}\n\n{task.payload.extra_instruction.strip()}"
            progress_callback(self._progress(task, source_root))
            with task_config_path(agent_config=self.agent_config, task=task) as config_path:

                def repair_progress(event: dict[str, Any]) -> None:
                    progress = self._progress(task, source_root)
                    progress.result_summary_json = json.dumps(
                        {"outputValidation": event}, ensure_ascii=False
                    )
                    progress_callback(progress)

                output_yaml = asyncio.run(
                    generate_validated(
                        stage="ui_case_generating",
                        inputs=input_text,
                        generate=lambda prompt: self.skill_runner(
                            input_text=prompt,
                            session_key=task.session_key,
                            skill_name=self.skill_name,
                            config_path=config_path,
                            workspace=str(workspace),
                            extra_instruction="",
                        ),
                        validate=_validate_ui_cases_yaml,
                        diagnostic_dir=workspace / "diagnostics" / "ui-output",
                        report=repair_progress,
                    )
                )
            case_count = _validate_ui_cases_yaml(output_yaml)
            return TaskResult(
                task_id=task.task_id,
                run_id=task.run_id,
                generate_task_id=task.generate_task_id,
                status=TaskStatus.SUCCESS,
                intermediate_json_text=json.dumps(
                    {
                        "sourceArchiveDownloadUrl": task.payload.source_archive_download_url,
                        "sourceRoot": str(source_root),
                        "caseCount": case_count,
                    },
                    ensure_ascii=False,
                ),
                output_yaml=output_yaml,
                result_summary_json=self._summary(task, "success", case_count, None),
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
            )
        except (OSError, ValueError, yaml.YAMLError) as error:
            return self._failure(task, started_at, str(error))

    def _failure(self, task: Task, started_at: datetime, error_message: str) -> TaskResult:
        return TaskResult(
            task_id=task.task_id,
            run_id=task.run_id,
            generate_task_id=task.generate_task_id,
            status=TaskStatus.FAILED,
            error_message=error_message,
            result_summary_json=self._summary(task, "failed", 0, error_message),
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _progress(task: Task, source_root: Path) -> TaskProgress:
        return TaskProgress(
            task_id=task.task_id,
            run_id=task.run_id,
            current_stage="ui_case_generating",
            stage_status="running",
            intermediate_json_text=json.dumps({"sourceRoot": str(source_root)}, ensure_ascii=False),
        )

    @staticmethod
    def _summary(task: Task, status: str, case_count: int, error_message: str | None) -> str:
        return build_task_result_summary(
            task=task,
            status=status,
            error_message=error_message,
            details={"caseCount": case_count},
        )


def _validate_ui_cases_yaml(output_yaml: str) -> int:
    parsed = parse_yaml(output_yaml)
    if isinstance(parsed, list):
        cases = parsed
    else:
        raise ValueError("UI 用例结果顶层必须是 YAML list")

    for case_index, case in enumerate(cases, start=1):
        _validate_ui_case(case, case_index)
    return len(cases)


def _validate_ui_case(case: object, case_index: int) -> None:
    if not isinstance(case, dict):
        raise ValueError(f"第 {case_index} 条 UI 用例必须是 mapping")
    required_fields = {"name", "enabled", "stepsJson", "orderNo"}
    if not required_fields.issubset(case):
        raise ValueError(f"第 {case_index} 条 UI 用例缺少必填字段")
    if not isinstance(case["name"], str) or not case["name"].strip():
        raise ValueError(f"第 {case_index} 条 UI 用例 name 必须是非空字符串")
    if not isinstance(case["enabled"], bool):
        raise ValueError(f"第 {case_index} 条 UI 用例 enabled 必须是布尔值")
    if not _is_integer(case["orderNo"]) or case["orderNo"] != case_index:
        raise ValueError("UI 用例 orderNo 必须从 1 开始跨用例连续递增")
    if not isinstance(case["stepsJson"], list):
        raise ValueError(f"第 {case_index} 条 UI 用例 stepsJson 必须是 list")

    for step_index, step in enumerate(case["stepsJson"], start=1):
        _validate_ui_step(step, case_index, step_index)


def _validate_ui_step(step: object, case_index: int, step_index: int) -> None:
    prefix = f"第 {case_index} 条 UI 用例的第 {step_index} 个步骤"
    if not isinstance(step, dict):
        raise ValueError(f"{prefix}必须是 mapping")
    try:
        step = draft_step_for_validation(step)
    except ValueError as exc:
        raise ValueError(f"{prefix}: {exc}") from exc
    required_fields = {"orderNo", "stepName", "keyword", "continueOnFailure", "enabled"}
    if not required_fields.issubset(step):
        raise ValueError(f"{prefix}缺少必填字段")
    if not _is_integer(step["orderNo"]) or step["orderNo"] != step_index:
        raise ValueError(f"{prefix} orderNo 必须从 1 开始连续递增")
    if not isinstance(step["stepName"], str) or not step["stepName"].strip():
        raise ValueError(f"{prefix} stepName 必须是非空字符串")
    if not isinstance(step["continueOnFailure"], bool):
        raise ValueError(f"{prefix} continueOnFailure 必须是布尔值")
    if not isinstance(step["enabled"], bool):
        raise ValueError(f"{prefix} enabled 必须是布尔值")

    keyword = step["keyword"]
    rule = UI_KEYWORD_RULES.get(keyword) if isinstance(keyword, str) else None
    if rule is None:
        raise ValueError(f"{prefix} keyword 不受支持: {keyword}")

    if rule.locator_required:
        locator_type = step.get("locatorType")
        locator_value = step.get("locatorValue")
        if not isinstance(locator_type, str) or locator_type not in VALID_UI_LOCATOR_TYPES:
            raise ValueError(f"{prefix} locatorType 不受支持或缺失: {locator_type}")
        if not isinstance(locator_value, str) or not locator_value.strip():
            raise ValueError(f"{prefix} locatorValue 必须是非空字符串")
    elif "locatorType" in step or "locatorValue" in step:
        raise ValueError(f"{prefix} keyword={keyword} 不应包含 locatorType/locatorValue")

    if rule.operation == "required":
        if "operationValue" not in step or step["operationValue"] is None:
            raise ValueError(f"{prefix} keyword={keyword} 必须包含 operationValue")
        if isinstance(step["operationValue"], str) and not step["operationValue"].strip():
            raise ValueError(f"{prefix} operationValue 不能为空")
    elif rule.operation == "forbidden" and "operationValue" in step:
        raise ValueError(f"{prefix} keyword={keyword} 不应包含 operationValue")

    if rule.comparator_required:
        if (
            not isinstance(step.get("comparator"), str)
            or step["comparator"] not in VALID_UI_COMPARATORS
        ):
            raise ValueError(f"{prefix} comparator 必须是 eq 或 contains")
    elif "comparator" in step:
        raise ValueError(f"{prefix} keyword={keyword} 不应包含 comparator")


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_ui_stage_yaml(output_yaml: str) -> int:
    """Reject draft fields/types that the control plane cannot accept before publishing."""
    from .completion import compile_case

    parsed = parse_yaml(output_yaml)
    if not isinstance(parsed, list):
        raise ValueError("UI 用例结果顶层必须是 YAML list")
    output_yaml = yaml.safe_dump(
        [compile_case(case, for_validation=True) for case in parsed], allow_unicode=True
    )
    count = _validate_ui_cases_yaml(output_yaml)
    case_fields = {"name", "enabled", "stepsJson", "orderNo"}
    step_fields = {
        "orderNo",
        "stepName",
        "keyword",
        "continueOnFailure",
        "enabled",
        "locatorType",
        "locatorValue",
        "operationValue",
        "comparator",
        "missingFields",
        "saveTo",
    }
    for case in parse_yaml(output_yaml):
        if set(case) - case_fields:
            raise ValueError("UI 用例包含不支持的字段")
        for raw_step in case["stepsJson"]:
            if set(raw_step) - step_fields:
                raise ValueError("UI 步骤包含不支持的字段")
            step = draft_step_for_validation(raw_step)
            validate_step_variables(step)
            normalize_save_to(step, field_path=f"用例 {case['orderNo']} 步骤 {step['orderNo']}")
            keyword, value = step["keyword"], step.get("operationValue")
            if keyword in {"sleep", "assert_visible", "assert_hidden"}:
                if not (
                    (_is_integer(value) and value >= 0)
                    or (
                        isinstance(value, str)
                        and (value.strip().isdigit() or TOKEN_PATTERN.search(value))
                    )
                ):
                    raise ValueError("等待时间必须是非负毫秒数")
            elif UI_KEYWORD_RULES[keyword].operation == "required" and not isinstance(value, str):
                raise ValueError("operationValue 必须是字符串")
    return count
