"""Start a single-case debug run after subscribing to its event stream."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from testing_agent.handlers.test_run import api_debug_stream, ui_debug_stream

router = APIRouter()

router.post("/test-debug-stream/api-case/{case_id}", response_class=StreamingResponse)(
    api_debug_stream
)
router.post("/test-debug-stream/ui-case/{case_id}", response_class=StreamingResponse)(
    ui_debug_stream
)
