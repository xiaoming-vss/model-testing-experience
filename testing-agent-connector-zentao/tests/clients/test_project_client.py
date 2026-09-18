import pytest

from app.clients.zentao.project_client import ZentaoProjectClient
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
async def test_project_client_passes_request_token() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoProjectClient(
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
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del action_name, json_body
        assert method == "GET"
        assert path == "/projects"
        assert params == {"browseType": "undone"}
        token = (headers or {}).get("token", "")
        attempts.append(token)
        return {"status": "success", "projects": [{"id": "1", "name": "Demo Project"}]}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    payload = await client.list_projects(params={"browseType": "undone"})

    assert payload["status"] == "success"
    assert attempts == ["request-token"]
    assert token_manager.get_token_calls == 1


@pytest.mark.anyio
async def test_project_client_get_project_uses_detail_path() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoProjectClient(
        ZentaoTomlConfig(base_url="https://zentao.example.com"),
        token_manager,
    )

    async def fake_request_json(
        method: str,
        path: str,
        action_name: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del action_name, params, json_body
        assert method == "GET"
        assert path == "/projects/2"
        assert headers == {"token": "request-token"}
        return {"status": "success", "project": {"id": "2", "name": "Demo Project"}}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    payload = await client.get_project(2)

    assert payload["project"]["id"] == "2"


@pytest.mark.anyio
async def test_project_client_get_project_requires_project_payload() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoProjectClient(
        ZentaoTomlConfig(base_url="https://zentao.example.com"),
        token_manager,
    )

    async def fake_request_json(
        method: str,
        path: str,
        action_name: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del method, path, action_name, params, headers, json_body
        return {"status": "success"}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    with pytest.raises(AppError):
        await client.get_project(2)
