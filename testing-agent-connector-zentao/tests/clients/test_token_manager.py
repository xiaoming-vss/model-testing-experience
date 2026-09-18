import pytest

from app.clients.zentao.token_manager import ZentaoTokenManager
from app.core.exceptions import AppError
from app.core.zentao_toml import ZentaoTomlConfig


@pytest.mark.anyio
async def test_token_manager_returns_request_token() -> None:
    manager = ZentaoTokenManager(
        ZentaoTomlConfig(
            base_url="https://zentao.example.com",
        ),
        "request-token",
    )

    first_token = await manager.get_token()
    second_token = await manager.get_token()

    assert first_token == "request-token"
    assert second_token == "request-token"


@pytest.mark.anyio
async def test_token_manager_requires_request_token() -> None:
    manager = ZentaoTokenManager(
        ZentaoTomlConfig(base_url="https://zentao.example.com"),
        "",
    )

    with pytest.raises(AppError) as exc_info:
        await manager.get_token()

    assert exc_info.value.message == (
        "Missing Zentao token. Provide it with `Authorization: Bearer <token>`."
    )
