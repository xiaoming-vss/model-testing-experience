"""禅道 Bug 到平台字段的唯一转换口径：导入预览与反向拉取共用（R20）。

纯函数模块：输入 `get_bugs_bugID` 返回的 `bug` 字典，输出规范化快照与平台
值；有损映射（优先级 2 等）不猜默认值，返回 None 交由调用方标记待映射
（Q04）。字段结构异常抛 `ValueError`，由服务层转业务错误。
"""

from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
from re import sub as _re_sub
from typing import Any

from testing_agent.core.enums import BugResolution, BugSeverity, BugStatus
from testing_agent.domain.rich_text import has_rich_text_content, sanitize_rich_text

TITLE_MAX_LENGTH = 200

REMOTE_SEVERITY = {
    "1": BugSeverity.FATAL,
    "2": BugSeverity.SERIOUS,
    "3": BugSeverity.NORMAL,
    "4": BugSeverity.MINOR,
}
# 禅道优先级四档与平台一一对应；优先级不再产生待映射（Q04，2026-10-09）。
REMOTE_PRIORITY = {"1": "urgent", "2": "high", "3": "medium", "4": "low"}


def map_severity(value: object) -> str | None:
    """禅道 1-4 映射平台严重程度；空、0 及未知值返回 None 待映射。"""
    key = str(value or "").strip()
    if key.endswith(".0"):
        key = key[:-2]
    severity = REMOTE_SEVERITY.get(key)
    return severity.value if severity else None


def map_priority(value: object) -> str | None:
    """禅道 1/2/3/4 无损映射平台优先级 紧急/高/中/低（Q04 优先级部分已关闭）。"""
    key = str(value or "").strip()
    if key.endswith(".0"):
        key = key[:-2]
    return REMOTE_PRIORITY.get(key)


def map_status(
    status: object, confirmed: object, resolution: object, resolved_build: object = ""
) -> dict[str, Any] | None:
    """主状态原值保存，确认标志与解决方案独立校验；无法映射返回 None（R24）。"""
    status_value = str(status or "").strip()
    if status_value not in BugStatus.values():
        return None
    resolution_value = str(resolution or "").strip()
    if status_value == BugStatus.ACTIVE.value:
        resolution_value = ""
    elif resolution_value not in BugResolution.values():
        return None
    return {
        "status": status_value,
        "confirmed": _flag(confirmed),
        "resolution": resolution_value,
        "resolvedBuild": str(resolved_build or "").strip(),
    }


def check_title(title: object) -> str:
    """标题非空且不超过平台长度限制，不静默截断。"""
    value = str(title or "").strip()
    if not value:
        raise ValueError("禅道 Bug 标题为空")
    if len(value) > TITLE_MAX_LENGTH:
        raise ValueError(f"禅道 Bug 标题超过平台 {TITLE_MAX_LENGTH} 字限制")
    return value


def _int_field(detail: dict, key: str, *, default: int | None = None) -> int | None:
    value = detail.get(key)
    if value is None or str(value).strip() == "":
        return default
    try:
        if isinstance(value, bool) or isinstance(value, float):
            raise ValueError()
        result = int(str(value).strip())
    except ValueError:
        raise ValueError(f"禅道 Bug 字段 {key} 编号异常") from None
    return result if result > 0 else default


def _flag(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _text_field(detail: dict, key: str) -> str:
    value = detail.get(key)
    return "" if value is None else str(value).strip()


class _ImageDetector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = False

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.found = True

    handle_startendtag = handle_starttag


def has_remote_images(raw_html: str) -> bool:
    """远端正文是否包含图片；此类正文必须等待文件管线，不能直接应用。"""
    if not raw_html:
        return False
    detector = _ImageDetector()
    detector.feed(raw_html)
    detector.close()
    return detector.found


def remote_description(raw_steps: object) -> dict[str, Any]:
    """远端 steps 的净化结果：完整净化文本、去图文本与内容摘要（R30/R41/R46）。"""
    raw = str(raw_steps or "")
    sanitized = sanitize_rich_text(raw)
    # R41 文本先行：剥掉图片标签后的净化文本，供图片待补时先落正文。
    text_only = sanitize_rich_text(_re_sub(r"<img\b[^>]*/?>|</img>", "", raw, flags=2))
    return {
        "sanitized": sanitized,
        "digest": sha256(sanitized.encode()).hexdigest(),
        "textOnly": text_only,
        "textOnlyDigest": sha256(text_only.encode()).hexdigest(),
        "hasImages": has_remote_images(raw),
        "hasContent": has_rich_text_content(sanitized),
    }


def remote_snapshot(detail: dict) -> dict[str, Any]:
    """把远端 Bug 详情规范化为参与导入、比对与来源留档的最小快照。

    不包含 steps 正文（可能很大），描述信息通过 `remote_description` 单独处理。
    """
    bug_id = _int_field(detail, "id")
    if bug_id is None:
        raise ValueError("禅道 Bug 详情缺少有效编号")
    title = check_title(detail.get("title"))
    return {
        "remoteBugId": bug_id,
        "title": title,
        "severity": str(detail.get("severity") or "").strip(),
        # 禅道 Bug 对象的优先级字段名为 pri；保留 priority 兼容读取。
        "priority": str(detail.get("pri") or detail.get("priority") or "").strip(),
        # 状态原值保留；是否可映射由 map_status 判定，未知状态走待处理（R39）。
        "status": str(detail.get("status") or "").strip(),
        "confirmed": _flag(detail.get("confirmed")),
        "resolution": _text_field(detail, "resolution"),
        "resolvedBuild": _text_field(detail, "resolvedBuild"),
        "duplicateBug": _int_field(detail, "duplicateBug", default=0) or 0,
        "activatedCount": _int_field(detail, "activatedCount", default=0) or 0,
        "execution": _int_field(detail, "execution", default=0) or 0,
        "story": _int_field(detail, "story", default=0) or 0,
        "project": _int_field(detail, "project", default=0) or 0,
        "assignedTo": _text_field(detail, "assignedTo"),
        "openedBy": _text_field(detail, "openedBy"),
        "openedDate": _text_field(detail, "openedDate"),
        "deleted": str(detail.get("deleted") or "").strip().lower() in {"1", "true", "yes", "on"},
    }
