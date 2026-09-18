"""
模板渲染模块
支持动态变量替换
"""

from __future__ import annotations

import re
import uuid
import random
import string
from datetime import datetime


def render_template(raw: str | None) -> str:
    """
    渲染模板字符串
    支持 {{ }} 语法的变量替换

    Args:
        raw: 原始字符串

    Returns:
        渲染后的字符串
    """
    if not raw:
        return ""

    def replace_match(match: re.Match) -> str:
        """替换匹配的模板表达式"""
        expr = match.group(1).strip()
        if not expr:
            return ""
        if expr.startswith("$"):
            return _evaluate_function(expr)
        return ""

    return re.sub(r"\{\{(.*?)\}\}", replace_match, raw)


def _evaluate_function(expr: str) -> str:
    """
    评估模板函数

    Args:
        expr: 函数表达式（以 $ 开头）

    Returns:
        函数执行结果
    """
    parts = _parse_function_args(expr)
    if not parts:
        return f"{{{{{expr}}}}}"

    fn_name = parts[0]
    args = parts[1:]

    if fn_name == "$timestamp":
        return str(int(datetime.now().timestamp()))
    elif fn_name == "$timestamp_ms":
        return str(int(datetime.now().timestamp() * 1000))
    elif fn_name == "$uuid":
        return str(uuid.uuid4())
    elif fn_name == "$randomInt":
        min_val = int(args[0]) if len(args) > 0 else 0
        max_val = int(args[1]) if len(args) > 1 else 9999
        return _random_int(min_val, max_val)
    elif fn_name == "$randomString":
        length = int(args[0]) if len(args) > 0 else 8
        return _random_string(length)
    elif fn_name == "$date":
        layout = args[0] if len(args) > 0 else "2006-01-02"
        return _format_date_by_go_layout(datetime.now(), layout)
    else:
        return f"{{{{{expr}}}}}"


def _parse_function_args(raw: str) -> list[str]:
    """
    解析函数参数

    Args:
        raw: 原始参数字符串

    Returns:
        参数列表
    """
    # 匹配引号内的字符串或非空白字符
    pattern = r'"[^"]*"|\'[^\']*\'|\S+'
    matches = re.findall(pattern, raw)
    # 去除引号
    return [m.strip("\"'") for m in matches]


def _random_int(min_val: int, max_val: int) -> str:
    """
    生成随机整数

    Args:
        min_val: 最小值
        max_val: 最大值

    Returns:
        随机整数字符串
    """
    lower = min(min_val, max_val)
    upper = max(min_val, max_val)
    value = random.randint(lower, upper)
    return str(value)


def _random_string(length: int) -> str:
    """
    生成随机字符串

    Args:
        length: 字符串长度

    Returns:
        随机字符串
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=max(length, 1)))[:length]


def _format_date_by_go_layout(date: datetime, layout: str) -> str:
    """
    按 Go 语言的 layout 格式化日期

    Args:
        date: 日期时间对象
        layout: Go 语言格式的 layout

    Returns:
        格式化后的日期字符串
    """
    # Go 语言的 layout 占位符映射
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
