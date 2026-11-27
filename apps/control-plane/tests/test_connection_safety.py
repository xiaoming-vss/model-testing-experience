"""Upstream failure text and embedded credentials never reach a user or the log."""

import httpx
import pytest

from testing_agent.services.connection_security import require_secure_scheme
from testing_agent.services.gitlab_auth import GitLabAuthProvider, normalize_gitlab_base_url
from testing_agent.services.gitlab_resource import GitLabResourceClient, GitLabResourceError

BASE_URL = "https://gitlab.example.test"


def _transport(status: int):
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text='{"message": "SECRET upstream detail"}')

    return httpx.MockTransport(handle)


@pytest.mark.asyncio
async def test_gitlab_auth_failure_reports_the_status_but_not_the_response_body():
    provider = GitLabAuthProvider(transport=_transport(401))

    with pytest.raises(RuntimeError, match="GitLab 鉴权失败，HTTP 401") as raised:
        await provider.validate(BASE_URL, "token")

    assert "SECRET" not in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 500])
async def test_gitlab_resource_failure_reports_the_status_but_not_the_response_body(status):
    client = GitLabResourceClient(transport=_transport(status))

    with pytest.raises(GitLabResourceError) as raised:
        await client._request_json(BASE_URL, "token", "/api/v4/groups", {}, allow_http=False)

    assert raised.value.status_code == status
    assert str(raised.value) == f"GitLab 资源查询失败，HTTP {status}"


@pytest.mark.asyncio
async def test_gitlab_transport_failure_reports_the_exception_type_only():
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("SECRET https://user:pass@host/path", request=request)

    client = GitLabResourceClient(transport=httpx.MockTransport(handle))

    with pytest.raises(GitLabResourceError) as raised:
        await client._request_json(BASE_URL, "token", "/api/v4/groups", {}, allow_http=False)

    assert str(raised.value) == "GitLab 请求失败: ConnectError"


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@gitlab.example.test",
        "https://user@gitlab.example.test",
        "http://user:pass@gitlab.example.test",
    ],
)
def test_addresses_with_embedded_credentials_are_rejected(url):
    # These addresses are logged and stored; the token has its own field.
    with pytest.raises(ValueError, match="用户名或密码"):
        require_secure_scheme(url, allow_http=True)
    with pytest.raises(ValueError, match="用户名或密码"):
        normalize_gitlab_base_url(url)


def test_plain_addresses_keep_working():
    require_secure_scheme("https://gitlab.example.test", allow_http=False)
    require_secure_scheme("http://gitlab.example.test", allow_http=True)
    with pytest.raises(ValueError, match="allowHttp"):
        require_secure_scheme("http://gitlab.example.test", allow_http=False)
