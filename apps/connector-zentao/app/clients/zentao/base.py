from typing import TYPE_CHECKING, Any

from app.core.exceptions import (
    ERR_ZENTAO_CONFIG,
    ERR_ZENTAO_INVALID_RESPONSE,
    AppError,
)
from app.core.http_client import HttpClientConfig, HttpJsonClient
from app.core.zentao_toml import ZentaoTomlConfig

if TYPE_CHECKING:
    from app.clients.zentao.token_manager import ZentaoTokenManager


class BaseZentaoClient:
    """Common Zentao client setup shared by module-specific clients."""

    def __init__(self, config: ZentaoTomlConfig) -> None:
        self._config = config
        self._http_client = HttpJsonClient(
            HttpClientConfig(
                base_url=config.api_base_url,
                timeout=config.timeout_seconds,
                verify=self._get_verify_value(),
                trust_env=False,
                follow_redirects=True,
            )
        )

    def _get_verify_value(self) -> bool | str:
        if self._config.ca_file:
            return self._config.ca_file
        return self._config.verify_ssl


class AuthenticatedZentaoClient(BaseZentaoClient):
    """Base client for Zentao endpoints that require a caller-supplied token."""

    def __init__(self, config: ZentaoTomlConfig, token_manager: "ZentaoTokenManager") -> None:
        super().__init__(config)
        self._token_manager = token_manager

    @property
    def is_configured(self) -> bool:
        return self._token_manager.is_ready

    async def request_json_with_token(
        self,
        *,
        method: str,
        path: str,
        action_name: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._ensure_configured()

        token = await self._token_manager.get_token()
        return await self._send_authenticated_request(
            method=method,
            path=path,
            action_name=action_name,
            token=token,
            params=params,
            json_body=json_body,
        )

    def ensure_success_payload(
        self,
        payload: dict[str, Any],
        *,
        invalid_message: str | None = None,
        required_keys: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if payload.get("status") != "success":
            raise AppError(
                ERR_ZENTAO_INVALID_RESPONSE,
                message=invalid_message or f"Zentao returned a failure payload: {payload}",
            )

        missing_keys = [key for key in required_keys if key not in payload]
        if missing_keys:
            raise AppError(
                ERR_ZENTAO_INVALID_RESPONSE,
                message=invalid_message or f"Zentao returned an invalid payload: {payload}",
            )

        return payload

    def _ensure_configured(self) -> None:
        if not self.is_configured:
            raise AppError(
                ERR_ZENTAO_CONFIG,
                message="Zentao base_url or request token is missing.",
            )

    async def _send_authenticated_request(
        self,
        *,
        method: str,
        path: str,
        action_name: str,
        token: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._http_client.request_json(
            method=method,
            path=path,
            action_name=action_name,
            params=params,
            headers={"token": token},
            json_body=json_body,
        )
