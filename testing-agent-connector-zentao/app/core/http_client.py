import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.exceptions import ERR_ZENTAO_INVALID_RESPONSE, ERR_ZENTAO_REQUEST, AppError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HttpClientConfig:
    base_url: str
    timeout: int = 15
    verify: bool | str = True
    trust_env: bool = False
    follow_redirects: bool = True
    default_headers: dict[str, str] = field(default_factory=dict)


class HttpJsonClient:
    """Shared HTTP client wrapper for JSON-based API calls."""

    def __init__(self, config: HttpClientConfig) -> None:
        self._config = config

    async def request_json(
        self,
        method: str,
        path: str,
        action_name: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_url = f"{self._config.base_url.rstrip('/')}/{path.lstrip('/')}"
        merged_headers = {
            "Accept": "application/json",
            **self._config.default_headers,
            **(headers or {}),
        }
        start = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                base_url=self._config.base_url,
                timeout=self._config.timeout,
                verify=self._config.verify,
                trust_env=self._config.trust_env,
                follow_redirects=self._config.follow_redirects,
            ) as client:
                response = await client.request(
                    method=method,
                    url=path,
                    params=params,
                    headers=merged_headers,
                    json=json_body,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.warning(
                "outbound_http_status_error",
                extra={
                    "action": action_name,
                    "method": method,
                    "url": request_url,
                    "status_code": exc.response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            message = (
                f"{action_name} failed for {request_url} with status "
                f"{exc.response.status_code}: {exc.response.text}"
            )
            raise AppError(
                ERR_ZENTAO_REQUEST,
                message=message,
            ) from exc
        except httpx.RequestError as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "outbound_http_request_error",
                extra={
                    "action": action_name,
                    "method": method,
                    "url": request_url,
                    "duration_ms": duration_ms,
                },
            )
            raise AppError(
                ERR_ZENTAO_REQUEST,
                message=(
                    f"{action_name} failed for {request_url}: {exc} "
                    f"(verify={self._config.verify}, trust_env={self._config.trust_env})"
                ),
            ) from exc

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "outbound_http_completed",
            extra={
                "action": action_name,
                "method": method,
                "url": request_url,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError(
                ERR_ZENTAO_INVALID_RESPONSE,
                message=f"{action_name} returned invalid JSON.",
            ) from exc
        if not isinstance(payload, dict):
            raise AppError(
                ERR_ZENTAO_INVALID_RESPONSE,
                message=f"{action_name} returned a non-object JSON response.",
            )
        return payload
