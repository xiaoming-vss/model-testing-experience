from fastapi import status

from app.schemas.response import ErrorCode

ERR_BAD_REQUEST = ErrorCode(
    code=42000,
    message="Request parameters are invalid.",
    http_status=status.HTTP_400_BAD_REQUEST,
)
ERR_VALIDATION = ErrorCode(
    code=42200,
    message="Request validation failed.",
    http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
)
ERR_INTERNAL_SERVER = ErrorCode(
    code=50000,
    message="Internal server error.",
    http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
)
ERR_ZENTAO_CONFIG = ErrorCode(
    code=51001,
    message="Zentao configuration is incomplete.",
    http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
)
ERR_ZENTAO_REQUEST = ErrorCode(
    code=51002,
    message="Zentao upstream request failed.",
    http_status=status.HTTP_502_BAD_GATEWAY,
)
ERR_ZENTAO_INVALID_RESPONSE = ErrorCode(
    code=51003,
    message="Zentao returned an invalid response.",
    http_status=status.HTTP_502_BAD_GATEWAY,
)


class AppError(Exception):
    def __init__(
        self,
        error_code: ErrorCode,
        *,
        message: str | None = None,
        errors: list[dict] | None = None,
    ) -> None:
        super().__init__(message or error_code.message)
        self.error_code = error_code
        self.message = message or error_code.message
        self.errors = errors


def new_bad_request(message: str) -> AppError:
    return AppError(ERR_BAD_REQUEST, message=message)
