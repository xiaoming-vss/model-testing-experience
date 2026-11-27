from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from testing_agent.services.connection_security import (
    require_secure_scheme,
    warn_if_insecure,
)


def normalize_gitlab_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("GitLab 地址不合法")
    if parsed.query or parsed.fragment:
        raise ValueError("GitLab 地址不能包含查询参数或片段")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("GitLab 地址不能包含用户名或密码，请只填写访问令牌")
    return normalized


class GitLabAuthProvider:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def validate(
        self,
        base_url: str,
        access_token: str,
        *,
        allow_http: bool = False,
        insecure_skip_verify: bool = False,
    ) -> None:
        normalized = normalize_gitlab_base_url(base_url)
        require_secure_scheme(normalized, allow_http=allow_http)
        warn_if_insecure(
            "gitlab",
            normalized,
            allow_http=allow_http,
            insecure_skip_verify=insecure_skip_verify,
        )
        url = f"{normalized}/api/v4/user"
        async with httpx.AsyncClient(
            timeout=30.0,
            transport=self._transport,
            verify=not insecure_skip_verify,
        ) as client:
            response = await client.get(url, headers={"PRIVATE-TOKEN": access_token})
        if response.status_code < 200 or response.status_code >= 300:
            # GitLab's response body may echo request data; report the status only.
            raise RuntimeError(f"GitLab 鉴权失败，HTTP {response.status_code}")
