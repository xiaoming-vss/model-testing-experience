from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from testing_agent.services.zentao_resource import truncate_error


def normalize_gitlab_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("GitLab 地址不合法")
    if parsed.query or parsed.fragment:
        raise ValueError("GitLab 地址不能包含查询参数或片段")
    return normalized


class GitLabAuthProvider:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def validate(self, base_url: str, access_token: str) -> None:
        url = f"{normalize_gitlab_base_url(base_url)}/api/v4/user"
        async with httpx.AsyncClient(timeout=30.0, transport=self._transport) as client:
            response = await client.get(url, headers={"PRIVATE-TOKEN": access_token})
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                f"GitLab 鉴权失败，HTTP {response.status_code}: {truncate_error(response.text)}"
            )
