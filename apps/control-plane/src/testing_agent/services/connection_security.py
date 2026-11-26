from __future__ import annotations

import logging
from urllib.parse import urlsplit

LOGGER = logging.getLogger(__name__)


def connection_security_flags(extra_json: dict | None) -> tuple[bool, bool]:
    extra = extra_json or {}
    allow_http = bool(extra.get("allowHttp", extra.get("allow_http", False)))
    insecure = bool(extra.get("insecureSkipVerify", extra.get("insecure_skip_verify", False)))
    return allow_http, insecure


def require_secure_scheme(base_url: str, *, allow_http: bool) -> None:
    parsed = urlsplit(str(base_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("服务地址不合法")
    if parsed.username is not None or parsed.password is not None:
        # The address is logged and stored; credentials belong in the token field only.
        raise ValueError("服务地址不能包含用户名或密码，请只填写访问令牌")
    if parsed.scheme == "http" and not allow_http:
        raise ValueError("HTTP 服务地址需要显式允许（allowHttp=true）")


def warn_if_insecure(
    provider: str,
    base_url: str,
    *,
    allow_http: bool,
    insecure_skip_verify: bool,
) -> None:
    parsed = urlsplit(str(base_url or "").strip())
    if parsed.scheme == "http":
        LOGGER.warning("%s connection uses plain HTTP: %s", provider, base_url)
    if insecure_skip_verify:
        LOGGER.warning("%s connection skips TLS certificate verification: %s", provider, base_url)
