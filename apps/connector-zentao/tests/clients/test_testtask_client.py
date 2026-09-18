import pytest

from app.clients.zentao.testtask_client import ZentaoTestTaskClient
from app.core.exceptions import AppError
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
async def test_testtask_client_passes_request_token() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoTestTaskClient(
        ZentaoTomlConfig(
            base_url="https://zentao.example.com",
        ),
        token_manager,
    )
    attempts: list[str] = []

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
        assert path == "/executions/11/testtasks"
        assert params == {"browseType": "all"}
        token = (headers or {}).get("token", "")
        attempts.append(token)
        return {
            "status": "success",
            "testtasks": [{"id": "101", "name": "Regression Test Task"}],
        }

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    payload = await client.list_testtasks(
        execution_id=11,
        params={"browseType": "all"},
    )

    assert payload["status"] == "success"
    assert attempts == ["request-token"]
    assert token_manager.get_token_calls == 1


@pytest.mark.anyio
async def test_testtask_client_get_testtask_uses_detail_path() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoTestTaskClient(
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
        del action_name, params, json_body
        assert method == "GET"
        assert path == "/testtasks/101"
        assert headers == {"token": "request-token"}
        return {"status": "success", "testtask": {"id": "101", "name": "Regression"}}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    payload = await client.get_testtask(101)

    assert payload["testtask"]["id"] == "101"


@pytest.mark.anyio
async def test_testtask_client_get_testtask_requires_testtask_payload() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoTestTaskClient(
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
        del method, path, action_name, params, headers, json_body
        return {"status": "success"}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    with pytest.raises(AppError):
        await client.get_testtask(101)
