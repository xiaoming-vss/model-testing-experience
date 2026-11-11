"""Named variable references inside UI step templates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

TOKEN_PATTERN = re.compile(r"\{\{(.*?)\}\}")
MODIFIERS = frozenset({"xpath"})
MAX_NAME_LENGTH = 120
FORBIDDEN_NAME_CHARACTERS = frozenset("{}|")
BUILTIN_PREFIX = "$"
DRAFT_DATA_PREFIX = "data."


@dataclass(frozen=True)
class VariableToken:
    name: str
    modifier: str
    start: int
    end: int


def parse_tokens(template: str | None) -> list[VariableToken]:
    """Return named-variable references; `$` built-in expressions are ignored."""
    if not template:
        return []
    tokens: list[VariableToken] = []
    for match in TOKEN_PATTERN.finditer(template):
        expression = match.group(1).strip()
        if not expression:
            raise ValueError("变量引用不能为空")
        if expression.startswith(BUILTIN_PREFIX):
            continue
        name, modifier = _split_expression(expression)
        _validate_name(name)
        if name.startswith(DRAFT_DATA_PREFIX):
            raise ValueError("草稿数据引用必须先完成编译，用例不能直接使用 data. 引用")
        tokens.append(VariableToken(name, modifier, match.start(), match.end()))
    return tokens


def validate_step_variables(step: dict[str, Any]) -> None:
    """Reject variable usage that the executor cannot render safely."""
    locator_type = str(step.get("locatorType") or "").strip().lower()
    locator_value = step.get("locatorValue")
    operation_value = step.get("operationValue")

    if isinstance(locator_value, str):
        validate_locator_tokens(locator_value, locator_type)

    if isinstance(operation_value, str):
        for token in parse_tokens(operation_value):
            if token.modifier:
                raise ValueError("操作值中的变量不支持修饰符")


def validate_locator_tokens(value: str, locator_type: str) -> None:
    tokens = parse_tokens(value)
    if not tokens:
        return

    if locator_type == "xpath":
        for token in tokens:
            if token.modifier != "xpath":
                raise ValueError("XPath 定位中的变量必须写成 {{名字|xpath}}")
            if _quoted_at(value, token.start):
                raise ValueError("XPath 中的变量不能自己加引号，由执行器生成安全字面量")
        return

    if locator_type == "css":
        for token in tokens:
            if token.modifier:
                raise ValueError("CSS 定位中的变量不接受修饰符，执行器按引号上下文转义")
        return

    if locator_type == "role" and value.lstrip().startswith("{"):
        raise ValueError("role 的 JSON 形式不支持变量，请改用 role::name")

    for token in tokens:
        if token.modifier:
            raise ValueError("该定位类型不支持变量修饰符")


def _split_expression(expression: str) -> tuple[str, str]:
    if "|" not in expression:
        return expression.strip(), ""
    name, modifier = expression.rsplit("|", 1)
    modifier = modifier.strip()
    if modifier not in MODIFIERS:
        raise ValueError(f"不支持的变量修饰符：{modifier or '(空)'}")
    return name.strip(), modifier


def _validate_name(name: str) -> None:
    if not name:
        raise ValueError("变量名不能为空")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"变量名不能超过 {MAX_NAME_LENGTH} 个字符")
    if FORBIDDEN_NAME_CHARACTERS.intersection(name):
        raise ValueError("变量名不能包含 { } 或 |")
    if any(character.isspace() for character in name):
        raise ValueError("变量名不能包含空白字符")


def _quoted_at(value: str, position: int) -> bool:
    """Detect whether an offset sits inside a single- or double-quoted region."""
    quote = ""
    for character in value[:position]:
        if not quote and character in "\"'":
            quote = character
        elif character == quote:
            quote = ""
    return bool(quote)
