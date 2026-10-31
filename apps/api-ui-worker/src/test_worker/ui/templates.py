"""
UI 步骤字段模板渲染。
按字段与定位类型转义命名变量，并为内置函数在一次渲染内保持同一取值。
"""

from __future__ import annotations

import random
import re
import string
import uuid
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from urllib.parse import quote as quote_url

_TOKEN = re.compile(r"\{\{(.*?)\}\}")
_CSS_IDENT_SAFE = frozenset(string.ascii_letters + string.digits + "_-")
_BASE_URL_NAME = "baseUrl"
_XPATH_MODIFIER = "xpath"
_URL_KEYWORDS = frozenset({"open"})


@dataclass
class RenderContext:
    """一次步骤渲染的上下文，内置函数取值在同一次渲染内复用。"""

    field: str = ""
    locator_type: str = ""
    keyword: str = ""
    builtins: dict[str, str] = dataclass_field(default_factory=dict)


def render_field(
    raw: str | None, variables: dict[str, str], context: RenderContext
) -> str:
    if not raw:
        return ""
    return _TOKEN.sub(lambda match: _replace(match, variables, context), raw)


def referenced_names(*templates: str | None) -> list[str]:
    """收集两个字段中引用的命名变量，保持首次出现顺序。"""
    names: list[str] = []
    for template in templates:
        if not template:
            continue
        for match in _TOKEN.finditer(template):
            expression = match.group(1).strip()
            if not expression or expression.startswith("$"):
                continue
            name, _ = _split_expression(expression)
            if name not in names:
                names.append(name)
    return names


def _replace(match: re.Match, variables: dict[str, str], context: RenderContext) -> str:
    expression = match.group(1).strip()
    if not expression:
        raise ValueError("变量引用不能为空")
    if expression.startswith("$"):
        return _builtin(expression, context.builtins)

    name, modifier = _split_expression(expression)
    value = _value_for(name, variables)
    return _escape(value, name, modifier, match.start(), match.string, context)


def _split_expression(expression: str) -> tuple[str, str]:
    if "|" not in expression:
        return expression.strip(), ""
    name, modifier = expression.rsplit("|", 1)
    modifier = modifier.strip()
    if modifier != _XPATH_MODIFIER:
        raise ValueError(f"不支持的变量修饰符：{modifier or '(空)'}")
    return name.strip(), modifier


def _value_for(name: str, variables: dict[str, str]) -> str:
    if name not in variables:
        raise ValueError(f"变量未定义：{name}")
    value = variables[name]
    if name == _BASE_URL_NAME and not value.strip():
        raise ValueError("环境未配置基础地址")
    return value


def _escape(
    value: str,
    name: str,
    modifier: str,
    start: int,
    template: str,
    context: RenderContext,
) -> str:
    if context.field == "locatorValue":
        if context.locator_type == "xpath":
            if modifier != _XPATH_MODIFIER:
                raise ValueError(
                    f"XPath 定位中的变量必须写成 {{名字|{_XPATH_MODIFIER}}}：{name}"
                )
            return xpath_literal(value)
        if context.locator_type == "css":
            if modifier:
                raise ValueError("CSS 定位中的变量不接受修饰符")
            return css_escape(
                value,
                _open_quote(template, start),
                _at_identifier_start(template, start),
            )
        if context.locator_type == "role" and template.lstrip().startswith("{"):
            raise ValueError("role 的 JSON 形式不支持变量")
        if modifier:
            raise ValueError("该定位类型不支持变量修饰符")
        return value

    if modifier:
        raise ValueError("操作值中的变量不支持修饰符")
    if context.keyword in _URL_KEYWORDS and name != _BASE_URL_NAME:
        return quote_url(value, safe="")
    return value


def xpath_literal(value: str) -> str:
    """生成 XPath 1.0 字符串字面量；同时含单双引号时使用 concat。"""
    if "'" not in value:
        return "'" + value + "'"
    if '"' not in value:
        return '"' + value + '"'
    return (
        "concat("
        + ", ".join(
            "'" + part + "'" if index % 2 == 0 else '"\'"'
            for index, part in enumerate(re.split(r"(')", value))
        )
        + ")"
    )


def css_escape(value: str, quote: str, at_identifier_start: bool = True) -> str:
    """按 CSS 字符串或标识符上下文转义取值。"""
    if quote:
        escaped = value.replace("\\", "\\\\")
        escaped = escaped.replace(quote, "\\" + quote)
        return escaped.replace("\n", "\\A ")
    parts: list[str] = []
    for index, character in enumerate(value):
        leading_digit = index == 0 and at_identifier_start and character.isdigit()
        leading_negative = (
            index == 0
            and at_identifier_start
            and character == "-"
            and len(value) > 1
            and value[1].isdigit()
        )
        if character in _CSS_IDENT_SAFE and not leading_digit and not leading_negative:
            parts.append(character)
        elif ord(character) > 0x7F:
            parts.append(character)
        else:
            parts.append("\\" + format(ord(character), "x") + " ")
    return "".join(parts)


def _at_identifier_start(value: str, position: int) -> bool:
    """变量是否紧跟在 CSS 标识符开头；前面已经是标识符字符时按标识符内部处理。"""
    if position == 0:
        return True
    previous = value[position - 1]
    if previous == "\\":
        return False
    return not (previous.isalnum() or previous in "_-" or ord(previous) > 0x7F)


def _open_quote(value: str, position: int) -> str:
    quote = ""
    for character in value[:position]:
        if not quote and character in "\"'":
            quote = character
        elif character == quote:
            quote = ""
    return quote


def _builtin(expression: str, cache: dict[str, str]) -> str:
    if expression not in cache:
        cache[expression] = _evaluate_function(expression)
    return cache[expression]


def _evaluate_function(expr: str) -> str:
    parts = _parse_function_args(expr)
    if not parts:
        return f"{{{{{expr}}}}}"

    fn_name = parts[0]
    args = parts[1:]

    if fn_name == "$timestamp":
        return str(int(datetime.now().timestamp()))
    if fn_name == "$timestamp_ms":
        return str(int(datetime.now().timestamp() * 1000))
    if fn_name == "$uuid":
        return str(uuid.uuid4())
    if fn_name == "$randomInt":
        min_val = int(args[0]) if len(args) > 0 else 0
        max_val = int(args[1]) if len(args) > 1 else 9999
        return _random_int(min_val, max_val)
    if fn_name == "$randomString":
        length = int(args[0]) if len(args) > 0 else 8
        return _random_string(length)
    if fn_name == "$date":
        layout = args[0] if len(args) > 0 else "2006-01-02"
        return _format_date_by_go_layout(datetime.now(), layout)
    return f"{{{{{expr}}}}}"


def _parse_function_args(raw: str) -> list[str]:
    pattern = r'"[^"]*"|\'[^\']*\'|\S+'
    matches = re.findall(pattern, raw)
    return [match.strip("\"'") for match in matches]


def _random_int(min_val: int, max_val: int) -> str:
    lower = min(min_val, max_val)
    upper = max(min_val, max_val)
    return str(random.randint(lower, upper))


def _random_string(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=max(length, 1)))[:length]


def _format_date_by_go_layout(date: datetime, layout: str) -> str:
    replacements = [
        ("2006", str(date.year)),
        ("01", str(date.month).zfill(2)),
        ("02", str(date.day).zfill(2)),
        ("15", str(date.hour).zfill(2)),
        ("04", str(date.minute).zfill(2)),
        ("05", str(date.second).zfill(2)),
    ]
    result = layout
    for token, value in replacements:
        result = result.replace(token, value)
    return result
