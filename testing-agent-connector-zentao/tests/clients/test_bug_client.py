import pytest

from app.clients.zentao.bug_client import ZentaoBugClient
from app.core.zentao_toml import ZentaoTomlConfig


class FakeTokenManager:
    def __init__(self, token: str = "request-token") -> None:
        self.token = token
        self.get_token_calls = 0

    @property
    def is_ready(self) -> bool:
        return True

    async def get_token(self) -> str:
        self.get_token_calls += 1
        return self.token


@pytest.mark.anyio
async def test_bug_client_list_execution_bugs_uses_execution_path() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoBugClient(
        ZentaoTomlConfig(base_url="https://zentao.example.com"),
        token_manager,
    )

    async def fake_request_json(
        method: str,
        path: str,
        action_name: str,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del action_name, json_body
        assert method == "GET"
        assert path == "/executions/11/bugs"
        assert params == {"browseType": "all", "recPerPage": 100, "pageID": 1}
        assert headers == {"token": "request-token"}
        return {"status": "success", "bugs": [{"id": 201, "title": "Crash on login"}]}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    payload = await client.list_execution_bugs(
        11,
        params={"browseType": "all", "recPerPage": 100, "pageID": 1},
    )

    assert payload["bugs"][0]["id"] == 201
    assert token_manager.get_token_calls == 1
