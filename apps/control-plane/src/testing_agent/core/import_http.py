"""Bound upload envelopes before FastAPI's multipart/JSON parser allocates them."""

from __future__ import annotations

import asyncio
import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from testing_agent.core.errors import AppError, app_error_payload
from testing_agent.core.import_limits import ImportLimits

_IMPORT_PATH = re.compile(
    r"/v1/(?:function-test-suites/[^/]+/cases|api-collections/[^/]+|ui-test-suites/[^/]+)/import/?"
)


class ImportEnvelopeMiddleware:
    def __init__(self, app: ASGIApp, limits: ImportLimits) -> None:
        self.app = app
        self.limits = limits
        self.active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not _IMPORT_PATH.fullmatch(scope["path"])
        ):
            await self.app(scope, receive, send)
            return
        if self.active >= self.limits.max_concurrent:
            await self.reject(scope, receive, send, 429, "导入处理繁忙，请稍后重试")
            return
        self.active += 1
        try:
            # Allow bounded multipart framing; the content budget is separately checked by parser.
            maximum = self.limits.max_bytes + 65536
            data = bytearray()
            try:
                async with asyncio.timeout(60):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(data) + len(chunk) > maximum:
                            await self.reject(scope, receive, send, 413, "导入请求超过大小限制")
                            return
                        data.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await self.reject(scope, receive, send, 408, "导入上传超时，请重试")
                return
            delivered = False

            async def replay() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    body = bytes(data)
                    data.clear()
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
        finally:
            self.active -= 1

    @staticmethod
    async def reject(scope: Scope, receive: Receive, send: Send, code: int, message: str) -> None:
        scope.setdefault("state", {})["http_business_code"] = code
        error = AppError(code, message, code)
        await JSONResponse(app_error_payload(error), status_code=code)(scope, receive, send)
