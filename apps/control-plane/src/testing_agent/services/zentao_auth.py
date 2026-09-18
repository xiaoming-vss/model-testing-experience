from __future__ import annotations

from dataclasses import dataclass
from posixpath import normpath
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from testing_agent.services.zentao_resource import truncate_error


@dataclass(slots=True)
class ZentaoAuthResult:
    access_token: str
    expires_at: Any | None = None


class ZentaoAuthProvider:
    async def authenticate(self, base_url: str, account: str, password: str) -> ZentaoAuthResult:
        token_url = build_zentao_token_url(base_url)
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            response = await client.post(
                token_url,
                json={"account": account, "password": password},
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                f"禅道鉴权失败，HTTP {response.status_code}: {truncate_error(response.text)}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"禅道 token 响应解析失败: {exc}") from exc

        token = _extract_token(body)
        if not token:
            raise RuntimeError("禅道 token 响应为空")
        return ZentaoAuthResult(access_token=token)


def build_zentao_token_url(base_url: str) -> str:
    parsed = urlparse(str(base_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("禅道地址不合法")

    trimmed_path = parsed.path.rstrip("/")
    if trimmed_path.endswith("/api.php/v1"):
        token_path = f"{trimmed_path}/tokens"
    elif trimmed_path.endswith("/api.php"):
        token_path = f"{trimmed_path}/v1/tokens"
    else:
        token_path = f"{trimmed_path}/api.php/v1/tokens"
    normalized_path = normpath(token_path)
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return urlunparse(parsed._replace(path=normalized_path, query="", fragment=""))


def _extract_token(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    token = body.get("token")
    if token:
        return str(token).strip()
    data = body.get("data")
    if isinstance(data, dict):
        return str(data.get("token") or "").strip()
    return ""
