import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import ERR_BAD_REQUEST, ERR_INTERNAL_SERVER, ERR_VALIDATION, AppError
from app.schemas.response import handle_error

logger = logging.getLogger(__name__)


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("app_error", exc_info=True)
    return handle_error(
        request,
        error_code=exc.error_code,
        message=exc.message,
        errors=exc.errors,
    )


async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning("request_validation_error", exc_info=True)
    unexpected_params = _get_unexpected_query_params(exc)
    if unexpected_params:
        return handle_error(
            request,
            error_code=ERR_BAD_REQUEST,
            message="Unsupported query parameter(s): " + ", ".join(unexpected_params),
        )
    return handle_error(request, error_code=ERR_VALIDATION, errors=exc.errors())


async def handle_unexpected_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("unexpected_error", exc_info=True)
    return handle_error(request, error_code=ERR_INTERNAL_SERVER)


def _get_unexpected_query_params(exc: RequestValidationError) -> list[str]:
    return sorted(
        {
            str(error["loc"][-1])
            for error in exc.errors()
            if error.get("type") == "extra_forbidden"
            and error.get("loc")
            and error["loc"][0] == "query"
        }
    )
