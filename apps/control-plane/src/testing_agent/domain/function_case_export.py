"""Pure platform-case to Zentao payload conversion; no persistence or remote access."""

from dataclasses import dataclass
from typing import Any, TypedDict

from testing_agent.core.errors import ErrFunctionTestCaseImportInvalid, dynamic_error
from testing_agent.domain.function_case_content import CaseContent


@dataclass(frozen=True, slots=True)
class FunctionCaseExportSource:
    case_id: str
    title: str
    preconditions: str
    steps: str
    expected_results: str
    priority: str
    content_json: dict[str, Any] | None = None


class ZentaoCasePayload(TypedDict):
    title: str
    module: int
    story: int
    pri: int
    precondition: str
    steps: list[str]
    expects: list[str]


def case_payload(
    case: FunctionCaseExportSource, *, module_id: int, story_id: int
) -> ZentaoCasePayload:
    content = case.content_json
    if content is not None:
        pairs = CaseContent.model_validate(content).steps
        steps = [step.action for step in pairs]
        expects = [step.expected for step in pairs]
    else:
        steps = split_zentao_lines(case.steps)
        expects = split_zentao_lines(case.expected_results)
    if not steps or any(not step.strip() for step in steps):
        raise dynamic_error(
            ErrFunctionTestCaseImportInvalid,
            f"用例[{case.case_id}]测试步骤不能为空",
        )
    if not expects or any(not expected.strip() for expected in expects):
        raise dynamic_error(
            ErrFunctionTestCaseImportInvalid,
            f"用例[{case.case_id}]预期结果不能为空",
        )
    steps, expects = normalize_zentao_steps_and_expects(steps, expects)
    return {
        "title": case.title.strip(),
        "module": module_id,
        "story": story_id,
        "pri": zentao_priority(case.priority),
        "precondition": case.preconditions.strip(),
        "steps": steps,
        "expects": expects,
    }


def split_zentao_lines(value: str) -> list[str]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in text.split("\n") if part.strip()]


def normalize_zentao_steps_and_expects(
    steps: list[str],
    expects: list[str],
) -> tuple[list[str], list[str]]:
    if len(steps) == len(expects):
        return steps, expects
    target = max(len(steps), len(expects))
    return (
        steps + [" "] * (target - len(steps)),
        expects + [" "] * (target - len(expects)),
    )


def zentao_priority(value: str) -> int:
    text = str(value or "").strip().upper().removeprefix("P")
    try:
        priority = int(text)
    except ValueError:
        return 3
    return priority if 1 <= priority <= 4 else 3
