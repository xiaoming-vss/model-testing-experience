"""
日志工具模块
提供简单的日志输出功能
"""

import sys
from datetime import datetime, timezone


def _write(level: str, message: str, meta: dict | None = None) -> None:
    """
    写入日志

    Args:
        level: 日志级别
        message: 日志消息
        meta: 附加元数据
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = ""
    if meta is not None:
        payload = f" {_serialize_meta(meta)}"
    sys.stdout.write(f"{timestamp} [{level}] {message}{payload}\n")


def _serialize_meta(meta: dict) -> str:
    """
    序列化元数据为 JSON 字符串

    Args:
        meta: 元数据字典

    Returns:
        JSON 字符串
    """
    import json
    return json.dumps(meta, ensure_ascii=False)


def info(message: str, meta: dict | None = None) -> None:
    """
    输出 INFO 级别日志

    Args:
        message: 日志消息
        meta: 附加元数据
    """
    _write("INFO", message, meta)


def warn(message: str, meta: dict | None = None) -> None:
    """
    输出 WARN 级别日志

    Args:
        message: 日志消息
        meta: 附加元数据
    """
    _write("WARN", message, meta)


def error(message: str, meta: dict | None = None) -> None:
    """
    输出 ERROR 级别日志

    Args:
        message: 日志消息
        meta: 附加元数据
    """
    _write("ERROR", message, meta)
