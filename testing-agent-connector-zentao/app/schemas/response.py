from dataclasses import dataclass
from typing import Any

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class Response[T](BaseModel):
    code: int
    message: str
    data: T


class ErrorResponse(BaseModel):
    code: int
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ErrorCode:
    code: int
    message: str
    http_status: int


def handle_success(
    request: Request,
    data: Any,
    *,
    code: int = 0,
    message: str = "ok",
    status_code: int = status.HTTP_200_OK,
) -> JSONResponse:
    if data is None:
        data = {}
    payload = Response[Any](
        code=code,
        message=message,
        data=data,
    )
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


def handle_error(
    request: Request,
    *,
    error_code: ErrorCode,
    message: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        code=error_code.code,
        message=message or error_code.message,
        data={},
        errors=_sanitize_json_value(errors),
    )
    return JSONResponse(
        status_code=error_code.http_status,
        content=jsonable_encoder(payload),
    )


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_sanitize_json_value(item) for item in value]
    return value
