"""Built-in template functions for API and UI requests.

This module is copied byte-for-byte into the control plane, which pre-renders the
request snapshot a run starts with. Change the worker copy first and keep both
identical. A function always resolves to text, and the same function keeps one
value within a single render.
"""

from __future__ import annotations

import random
import re
import string
import time
import uuid
from datetime import datetime

_FUNCTION_ARGS = re.compile(r'"[^"]*"|\'[^\']*\'|\S+')
_RANDOM_ALPHABET = string.ascii_letters + string.digits
# Go reference-time tokens, matched longest first so one pass never rewrites a year.
_DATE_TOKENS = ("2006", "01", "02", "15", "04", "05")


def is_function(expression: str) -> bool:
    return expression.startswith("$")


def evaluate_function(expression: str, cache: dict[str, str]) -> str:
    """Resolve ``{{$name args}}``; an unknown function stays as written."""
    if expression not in cache:
        cache[expression] = _evaluate(expression)
    return cache[expression]


def _evaluate(expression: str) -> str:
    parts = [part.strip("\"'") for part in _FUNCTION_ARGS.findall(expression)]
    if not parts:
        return "{{" + expression + "}}"
    name, args = parts[0], parts[1:]
    if name == "$timestamp":
        return str(int(time.time()))
    if name == "$timestamp_ms":
        return str(int(time.time() * 1000))
    if name == "$now":
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if name == "$date":
        return format_date(datetime.now(), args[0] if args else "2006-01-02")
    if name == "$uuid":
        return str(uuid.uuid4())
    if name == "$randomInt":
        first = int(args[0]) if len(args) > 0 else 0
        second = int(args[1]) if len(args) > 1 else 9999
        return str(random.randint(min(first, second), max(first, second)))
    if name == "$randomString":
        length = int(args[0]) if args else 8
        return "".join(random.choices(_RANDOM_ALPHABET, k=max(length, 1)))[:length]
    return "{{" + expression + "}}"


def format_date(date: datetime, layout: str) -> str:
    """Render a Go-style layout such as ``2006-01-02 15:04:05`` for ``date``."""
    values = {
        "2006": str(date.year),
        "01": str(date.month).zfill(2),
        "02": str(date.day).zfill(2),
        "15": str(date.hour).zfill(2),
        "04": str(date.minute).zfill(2),
        "05": str(date.second).zfill(2),
    }
    out: list[str] = []
    index = 0
    while index < len(layout):
        token = ""
        for candidate in _DATE_TOKENS:
            if layout.startswith(candidate, index):
                token = candidate
                break
        if token:
            out.append(values[token])
            index += len(token)
        else:
            out.append(layout[index])
            index += 1
    return "".join(out)
