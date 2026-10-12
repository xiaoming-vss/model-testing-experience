"""富文本描述的白名单消毒与图片引用提取。

Bug 问题描述以 HTML 存储并在详情页原样渲染，因此入库前必须消毒：
只重建白名单内的结构与属性，其余内容（含 script/style 子树、注释、
事件属性、src/href）一律丢弃；文本节点重新转义。编辑器本身不提供
链接与图片外链能力，这里也不保留任何 URL 属性。
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

# 结构与文本标签；img 只保留 data-file-id 属性，渲染时再换取签名下载地址。
ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "hr",
        "strong",
        "em",
        "u",
        "s",
        "h1",
        "h2",
        "h3",
        "ul",
        "ol",
        "li",
        "blockquote",
        "pre",
        "code",
        "img",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
    }
)
VOID_TAGS = frozenset({"br", "hr", "img"})
ALLOWED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "img": frozenset({"data-file-id"}),
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan"}),
}
# 这些标签的子内容整体丢弃，避免样式/脚本内容以转义文本形式残留。
DROP_SUBTREES = frozenset({"script", "style", "iframe", "object", "embed", "svg", "math"})

_FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open_tags: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag, attrs):
        if self.drop_depth:
            if tag in DROP_SUBTREES and tag not in VOID_TAGS:
                self.drop_depth += 1
            return
        if tag in DROP_SUBTREES:
            self.drop_depth = 1
            return
        if tag not in ALLOWED_TAGS:
            return
        rendered = tag
        for name, value in attrs:
            if tag in ALLOWED_ATTRIBUTES and name in ALLOWED_ATTRIBUTES[tag]:
                value = value or ""
                if name == "data-file-id" and not _FILE_ID_PATTERN.match(value):
                    continue
                if name in {"colspan", "rowspan"} and (
                    len(value) > 3
                    or not value.isascii()
                    or not value.isdigit()
                    or not 1 <= int(value) <= 100
                ):
                    continue
                rendered += f' {name}="{html.escape(value, quote=True)}"'
        if tag in VOID_TAGS:
            self.out.append(f"<{rendered}>")
        else:
            self.out.append(f"<{rendered}>")
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in VOID_TAGS:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.drop_depth:
            if tag in DROP_SUBTREES:
                self.drop_depth -= 1
            return
        if tag in self.open_tags:
            while self.open_tags:
                opened = self.open_tags.pop()
                self.out.append(f"</{opened}>")
                if opened == tag:
                    break

    def handle_data(self, data):
        if not self.drop_depth and data:
            self.out.append(html.escape(data))

    def close(self):
        super().close()
        while self.open_tags:
            self.out.append(f"</{self.open_tags.pop()}>")


def sanitize_rich_text(raw: str) -> str:
    """消毒任意 HTML 输入；空输入返回空串。"""
    if not raw or not raw.strip():
        return ""
    parser = _Sanitizer()
    parser.feed(raw)
    parser.close()
    return "".join(parser.out)


def extract_file_ids(clean_html: str) -> list[str]:
    """按出现顺序提取已消毒 HTML 里的去重文件引用。"""
    seen: set[str] = set()
    file_ids: list[str] = []

    class _Collector(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag != "img":
                return
            for name, value in attrs:
                if name == "data-file-id" and value and value not in seen:
                    seen.add(value)
                    file_ids.append(value)

    collector = _Collector(convert_charrefs=True)
    collector.feed(clean_html)
    collector.close()
    return file_ids


def has_rich_text_content(clean_html: str) -> bool:
    """消毒后的正文必须含文字或有效内嵌图片。"""
    text = html.unescape(re.sub(r"<[^>]*>", "", clean_html)).strip()
    return bool(text or extract_file_ids(clean_html))
