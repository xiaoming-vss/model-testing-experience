from app.core.exceptions import ERR_BAD_REQUEST, AppError
from app.core.zentao_toml import ZentaoTomlConfig


class ZentaoTokenManager:
    """Provides the Zentao token supplied by the caller for a single request."""

    def __init__(self, config: ZentaoTomlConfig, request_token: str) -> None:
        self._config = config
        self._request_token = request_token.strip()

    @property
    def is_ready(self) -> bool:
        return bool(self._config.base_url and self._request_token)

    async def get_token(self) -> str:
        if self._request_token:
            return self._request_token
        raise AppError(
            ERR_BAD_REQUEST,
            message=("Missing Zentao token. Provide it with `Authorization: Bearer <token>`."),
        )
