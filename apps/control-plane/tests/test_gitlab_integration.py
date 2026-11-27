import httpx
import pytest

from testing_agent.services.gitlab_auth import GitLabAuthProvider
from testing_agent.services.integration_credentials import IntegrationCredentialCipher


def test_integration_credential_cipher_round_trips_without_exposing_plaintext():
    cipher = IntegrationCredentialCipher("stable-production-secret")

    encrypted = cipher.encrypt("glpat-secret-token")

    assert encrypted.startswith("enc:v1:")
    assert "glpat-secret-token" not in encrypted
    assert cipher.decrypt(encrypted) == "glpat-secret-token"


def test_integration_credential_cipher_rejects_a_different_key():
    encrypted = IntegrationCredentialCipher("first-key").encrypt("glpat-secret-token")

    with pytest.raises(ValueError, match="无法解密"):
        IntegrationCredentialCipher("second-key").decrypt(encrypted)


@pytest.mark.parametrize(
    "secret",
    ["", "change-me", "replace-with-local-integration-key"],
)
def test_integration_credential_cipher_rejects_missing_or_placeholder_keys(secret):
    with pytest.raises(ValueError, match="安全的集成凭据加密密钥"):
        IntegrationCredentialCipher(secret)


@pytest.mark.asyncio
async def test_gitlab_auth_validates_with_user_endpoint_without_returning_profile():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"id": 42, "username": "zhangsan", "name": "张三"},
        )

    provider = GitLabAuthProvider(transport=httpx.MockTransport(respond))

    result = await provider.validate(
        "https://gitlab.example.com/",
        "glpat-secret-token",
    )

    assert result is None
    assert str(requests[0].url) == "https://gitlab.example.com/api/v4/user"
    assert requests[0].headers["PRIVATE-TOKEN"] == "glpat-secret-token"


@pytest.mark.asyncio
async def test_gitlab_auth_rejects_http_without_opt_in():
    provider = GitLabAuthProvider(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )

    with pytest.raises(ValueError, match="allowHttp"):
        await provider.validate("http://gitlab.example.com", "glpat-secret-token")
