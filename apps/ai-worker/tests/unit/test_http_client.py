import sys
import unittest
import unittest.mock
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import httpx

from testing_agent_ai_worker.platform.http_client import (
    PlatformHttpClient,
    lease_rejected,
)


class PlatformHttpClientTests(unittest.TestCase):
    def test_headers_use_x_worker_token_name(self) -> None:
        client = PlatformHttpClient(
            base_url="https://platform.example.com",
            worker_token="worker-secret",
        )

        headers = client._headers()

        self.assertEqual(headers["X-Worker-Token"], "worker-secret")
        self.assertNotIn("X-Worker-Key", headers)


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "PATCH", "https://platform.example.com/internal/ai-worker/tasks/t/progress"
    )
    return httpx.HTTPStatusError(
        "rejected", request=request, response=httpx.Response(status, request=request)
    )


class LeaseRejectionTests(unittest.TestCase):
    def test_only_a_lost_lease_is_a_rejection(self) -> None:
        # The control plane uses these when the execution is no longer this worker's.
        for status in (401, 403, 404, 409, 410):
            self.assertTrue(lease_rejected(_status_error(status)), status)
        # A wrong request, throttling or an outage says nothing about the lease.
        for status in (400, 422, 429, 500, 503):
            self.assertFalse(lease_rejected(_status_error(status)), status)

        self.assertFalse(lease_rejected(httpx.ConnectError("unreachable")))
        self.assertFalse(lease_rejected(RuntimeError("not an HTTP failure")))


class RequestTimeoutTests(unittest.TestCase):
    def test_a_callers_bound_can_only_shorten_the_configured_timeout(self) -> None:
        client = PlatformHttpClient(base_url="https://platform.example.com", timeout_seconds=60)

        self.assertEqual(60, client._timeout(None))
        self.assertEqual(15, client._timeout(15))
        self.assertEqual(60, client._timeout(120))
        self.assertEqual(0.1, client._timeout(0))

    def test_every_json_call_sends_its_timeout_to_httpx(self) -> None:
        client = PlatformHttpClient(base_url="https://platform.example.com", timeout_seconds=60)
        context = unittest.mock.MagicMock()
        context.__enter__.return_value = context
        with unittest.mock.patch.object(httpx, "Client", return_value=context) as factory:
            client.post("/p", json_body={}, timeout_seconds=15)
            client.get("/g", timeout_seconds=5)
            client.patch("/h", json_body={})

        self.assertEqual(
            [15, 5, 60],
            [call.kwargs["timeout"] for call in factory.call_args_list],
        )


if __name__ == "__main__":
    unittest.main()
