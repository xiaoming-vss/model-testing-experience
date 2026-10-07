import hashlib
import unittest
from unittest.mock import patch

import httpx

from testing_agent_ai_worker.platform.http_client import PlatformHttpClient


class SignedDownloadTests(unittest.TestCase):
    def test_platform_conflict_preserves_business_reason_without_request_url(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(
                409, json={"code": 2203, "message": "需求原文件未存储到 S3，请重新上传", "data": {}}
            )

        with self.assertRaises(httpx.HTTPStatusError) as captured:
            self.run_client(handler)
        self.assertIn("需求原文件未存储到 S3，请重新上传", str(captured.exception))
        self.assertNotIn("https://platform.test", str(captured.exception))
        self.assertEqual(len(calls), 1)

    def test_non_json_authorization_error_has_safe_status_message(self):
        with self.assertRaises(httpx.HTTPStatusError) as captured:
            self.run_client(lambda _: httpx.Response(503, content=b"upstream unavailable"))
        self.assertIn("HTTP 503", str(captured.exception))
        self.assertNotIn("https://platform.test", str(captured.exception))

    def run_client(self, handler):
        original = httpx.Client
        with (
            patch(
                "testing_agent_ai_worker.platform.http_client.httpx.Client",
                side_effect=lambda **kwargs: original(
                    transport=httpx.MockTransport(handler), **kwargs
                ),
            ),
            patch("testing_agent_ai_worker.platform.http_client.time.sleep"),
        ):
            client = PlatformHttpClient("https://platform.test", "secret")
            return client.get_signed_file_bytes("/document")

    def test_direct_download_has_no_worker_credentials(self):
        seen = []

        def handler(request):
            seen.append(request)
            if request.url.host == "platform.test":
                self.assertEqual(request.headers["X-Worker-Token"], "secret")
                return httpx.Response(
                    200,
                    json={
                        "url": "https://s3.test/key?signature=secret",
                        "size": 5,
                        "sha256": hashlib.sha256(b"hello").hexdigest(),
                    },
                )
            self.assertNotIn("X-Worker-Token", request.headers)
            self.assertNotIn("Authorization", request.headers)
            return httpx.Response(200, content=b"hello")

        self.assertEqual(self.run_client(handler), b"hello")
        self.assertEqual(len(seen), 2)

    def test_expiry_requests_new_ticket(self):
        calls = {"platform": 0, "s3": 0}

        def handler(request):
            if request.url.host == "platform.test":
                calls["platform"] += 1
                return httpx.Response(
                    200,
                    json={
                        "url": "https://s3.test/key",
                        "size": 5,
                        "sha256": hashlib.sha256(b"hello").hexdigest(),
                    },
                )
            calls["s3"] += 1
            return (
                httpx.Response(403) if calls["s3"] == 1 else httpx.Response(200, content=b"hello")
            )

        self.assertEqual(self.run_client(handler), b"hello")
        self.assertEqual(calls, {"platform": 2, "s3": 2})

    def test_checksum_failure_is_not_used(self):
        def handler(request):
            if request.url.host == "platform.test":
                return httpx.Response(
                    200,
                    json={
                        "url": "https://s3.test/key?secret=hidden",
                        "size": 5,
                        "sha256": "0" * 64,
                    },
                )
            return httpx.Response(200, content=b"hello")

        with self.assertRaisesRegex(ValueError, "checksum"):
            self.run_client(handler)

    def test_binary_requirement_download_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Expected S3 download ticket"):
            self.run_client(lambda _: httpx.Response(200, content=b"legacy"))

    def test_foreign_authorization_url_is_rejected(self):
        with self.assertRaises(ValueError):
            PlatformHttpClient("https://platform.test", "secret").get_signed_file_bytes(
                "https://foreign.test/key"
            )
