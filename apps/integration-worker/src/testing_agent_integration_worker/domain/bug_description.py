"""Pure native-image routing and description comparison, kept compatible with CP fixtures."""

import hashlib
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit, urlunsplit


class DescriptionError(Exception):
    def __init__(self, status, message, http_status):
        super().__init__(message)


def source_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def image_id(src, instance):
    internal = re.fullmatch(r"\{([1-9][0-9]*)\.(?:png|jpg|jpeg|gif|webp|bmp)\}", src)
    if internal:
        return internal[1]
    url = urlsplit(src)
    if url.scheme not in {"", "http", "https"}:
        return None
    if url.netloc and url.netloc != urlsplit(instance).netloc:
        return None
    query = parse_qs(url.query)
    if query.get("m") == ["file"] and query.get("f") == ["read"]:
        return (query.get("fileID") or [None])[0]
    path = re.search(r"(?:^|/)file-read-([1-9][0-9]*)\.(?:png|jpg|jpeg|gif|webp|bmp)$", url.path)
    return path[1] if path else None


def canonical(value, instance="", *, legacy_encoded=False):
    """Ignore presentation attributes and normalize native image routing only."""
    parts: list[tuple[Any, ...]] = []

    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "img":
                src = dict(attrs).get("src", "")
                # Only the recovery comparison decodes legacy brace URLs. Such
                # URLs are broken, and must never count as successful readback.
                if (
                    legacy_encoded
                    and src != unquote(src)
                    and re.fullmatch(r"\{[1-9][0-9]*\.(?:png|jpg|jpeg)\}", unquote(src))
                ):
                    src = unquote(src)
                parts.append(("img", image_id(src, instance) or src))
            else:
                parts.append(("tag", tag, tuple(sorted(attrs))))

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)

        def handle_endtag(self, tag):
            if tag not in {"img", "br", "hr"}:
                parts.append(("end", tag))

        def handle_data(self, text):
            if text.strip():
                parts.append(("text", text))

    parser = Parser(convert_charrefs=True)
    parser.feed(value)
    parser.close()
    return parts


def unresolved_legacy_images(value):
    unresolved = False

    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            nonlocal unresolved
            if tag == "img" and re.fullmatch(
                r"\{[1-9][0-9]*\.(?:png|jpg|jpeg)\}",
                unquote(dict(attrs).get("src", "")),
            ):
                unresolved = True

    parser = Parser(convert_charrefs=True)
    parser.feed(value)
    return unresolved


def native_file_metadata(file, instance, remote_bug_id, descriptions):
    """Fill an inline file's route from already observed, ownership-checked HTML."""
    if file.get("url"):
        native_image_url(file, instance, remote_bug_id)
        return file
    identifier = str(file.get("id"))
    paths = []

    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "img":
                value = dict(attrs).get("src", "")
                if image_id(value, instance) == identifier:
                    paths.append(value)

    for description in descriptions:
        if isinstance(description, str):
            Parser(convert_charrefs=True).feed(description)
    for path in paths:
        candidate = {**file, "url": path}
        try:
            native_image_url(candidate, instance, remote_bug_id)
            return candidate
        except DescriptionError:
            continue
    raise DescriptionError(409, "缺少已确认的原生图片读取路径，请保持核对", 409)


def native_image_url(file, instance, remote_bug_id):
    """Convert an ownership-checked native download link into its read route."""
    if (
        file.get("objectType") != "bug"
        or str(file.get("objectID")) != str(remote_bug_id)
        or str(file.get("deleted", "0")).lower() in {"1", "true"}
    ):
        raise DescriptionError(409, "禅道图片不属于原 Bug 或已删除", 409)
    extension = str(file.get("extension", "")).lower()
    if extension not in {"png", "jpg", "jpeg"}:
        raise DescriptionError(400, "禅道图片格式不支持", 400)
    value = file.get("url")
    if not isinstance(value, str) or not value:
        raise DescriptionError(409, "禅道未返回图片读取路径", 409)
    url = urlsplit(value)
    if (
        url.scheme not in {"", "http", "https"}
        or url.username
        or url.password
        or url.fragment
        or (url.netloc and url.netloc != urlsplit(instance).netloc)
    ):
        raise DescriptionError(409, "禅道图片路径与原实例不一致", 409)
    identifier = str(file.get("id"))
    query = parse_qs(url.query)
    if (
        query.get("m") == ["file"]
        and query.get("f") in (["download"], ["read"])
        and query.get("fileID") == [identifier]
        and url.path.rsplit("/", 1)[-1] == "index.php"
    ):
        # Rebuild only route fields; never copy tokens from a returned URL.
        path, search = (
            url.path,
            urlencode(
                {
                    "m": "file",
                    "f": "read",
                    "t": extension,
                    "fileID": identifier,
                }
            ),
        )
    elif not url.query and re.search(
        rf"(?:^|/)file-(?:download|read)-{re.escape(identifier)}(?:-[0-9]+)*\.(?:json|html|png|jpg|jpeg)$",
        url.path,
    ):
        path = re.sub(
            rf"file-(?:download|read)-{re.escape(identifier)}(?:-[0-9]+)*\.[a-z]+$",
            f"file-read-{identifier}.{extension}",
            url.path,
        )
        search = ""
    else:
        raise DescriptionError(409, "禅道图片路径无法识别，请核对实例配置", 409)
    relative = urlunsplit(("", "", path, search, ""))
    return urljoin(instance.rstrip("/") + "/", relative)
