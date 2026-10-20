"""Safe HTTP diagnostics: correlation, route templates and message-free tracebacks."""

import json
import logging
import re
import traceback
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from testing_agent.core.errors import ErrInternalServerError, app_error_payload

LOGGER_NAME = "testing_agent.http"
logger = logging.getLogger(LOGGER_NAME)
_request_id: ContextVar[str | None] = ContextVar("http_request_id", default=None)
_UUID = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "TRACE"}


def current_request_id() -> str | None:
    return _request_id.get()


class ResponseAborted(RuntimeError):
    """The response has started and cannot be replaced with an error envelope."""


def route_template(scope: Scope) -> str:
    """Read only framework-owned templates, never interpolate request path parameters."""
    route = scope.get("route")
    # The locked FastAPI version retains included-router prefixes in this context,
    # while scope["route"] refers to the original, unprefixed route.
    context = scope.get("fastapi", {}).get("effective_route_context")
    if context is not None and getattr(context, "original_route", None) is route:
        path = getattr(context, "path", None)
        if isinstance(path, str):
            return path
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "<unmatched>"


def safe_exception_trace(error: BaseException) -> list[dict[str, object]]:
    """Never format exception messages, source lines or frame local variables."""
    pending = [error]
    seen: set[int] = set()
    result: list[dict[str, object]] = []
    while pending and len(result) < 8:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        frames = []
        for frame, line in traceback.walk_tb(item.__traceback__):
            frames.append(
                {
                    "module": frame.f_globals.get("__name__", "<unknown>"),
                    "function": frame.f_code.co_name,
                    "line": line,
                }
            )
            if len(frames) >= 40:
                break
        result.append({"type": type(item).__name__, "frames": frames})
        if isinstance(item, BaseExceptionGroup):
            pending.extend(item.exceptions[:8])
        if item.__cause__ is not None:
            pending.append(item.__cause__)
        elif not item.__suppress_context__ and item.__context__ is not None:
            pending.append(item.__context__)
    return result


class RequestDiagnosticsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = [
            value for key, value in scope.get("headers", []) if key.lower() == b"x-request-id"
        ]
        request_id = (
            supplied[0].decode("ascii")
            if len(supplied) == 1 and _UUID.fullmatch(supplied[0])
            else str(uuid4())
        )
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = _request_id.set(request_id)
        started = perf_counter()
        response_started = False
        status = 499
        failure = None

        async def tracked_send(message: Message) -> None:
            nonlocal response_started, status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                message = {
                    **message,
                    "headers": [*headers, (b"x-request-id", request_id.encode("ascii"))],
                }
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            failure = safe_exception_trace(exc)
            if response_started:
                raise ResponseAborted(
                    "HTTP response aborted; see correlated safe diagnostic"
                ) from None
            state["http_business_code"] = ErrInternalServerError.code
            response = JSONResponse(
                status_code=500, content=app_error_payload(ErrInternalServerError)
            )
            await response(scope, receive, tracked_send)
        finally:
            try:
                route = route_template(scope)
                code = state.get("http_business_code")
                record = {
                    "request_id": request_id,
                    "method": scope.get("method") if scope.get("method") in _METHODS else "OTHER",
                    "route": route,
                    "status": status,
                    "business_code": code if type(code) is int else None,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                }
                level = logging.INFO
                if failure is not None:
                    record["exceptions"] = failure
                    level = logging.ERROR
                elif (
                    status < 400
                    and route.startswith("/internal/")
                    and route.endswith(("/claim", "/heartbeat"))
                ):
                    level = logging.DEBUG
                logger.log(level, json.dumps(record, ensure_ascii=True))
            finally:
                _request_id.reset(token)
