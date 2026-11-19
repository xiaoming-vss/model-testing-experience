import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class WorkerConventionTests(unittest.TestCase):
    def test_document_covers_required_topics_and_projects(self):
        text = source("docs/agents/worker-conventions.md")
        for topic in (
            "健康检查",
            "心跳与租约",
            "回传失败与恢复",
            "关闭与状态映射",
            "快照与身份字段",
        ):
            self.assertIn(topic, text)
        for project in (
            "ai-worker",
            "api-ui-worker",
            "integration-worker",
            "perf-worker",
        ):
            self.assertIn(project, text)

    def test_http_health_workers_share_probe_contract(self):
        ai = source("apps/ai-worker/src/testing_agent_ai_worker/app/health.py")
        api = source("apps/api-ui-worker/src/test_worker/health.py")
        for text in (ai, api):
            self.assertIn('HEALTH_PATH = "/healthz"', text)
            self.assertIn("DEFAULT_HEALTH_PORT = 8080", text)
            self.assertIn('body = b"ok\\n"', text)
            self.assertIn("def health_port_from_env() -> int | None:", text)
        self.assertIn("TESTING_AGENT_HEALTH_PORT", ai)
        self.assertIn("TEST_WORKER_HEALTH_PORT", api)

    def test_file_health_workers_share_probe_contract(self):
        perf = source("apps/perf-worker/src/testing_agent_perf_worker/worker/health.py")
        integration = source(
            "apps/integration-worker/src/testing_agent_integration_worker/worker/lifecycle.py"
        )
        for text in (perf, integration):
            self.assertIn('"pid"', text)
            self.assertIn('"progressAt"', text)
            self.assertIn("os.kill", text)
            self.assertIn("max_age", text)
        self.assertIn(
            "--healthcheck", source("apps/perf-worker/src/testing_agent_perf_worker/main.py")
        )
        self.assertIn(
            "--healthcheck",
            source("apps/integration-worker/src/testing_agent_integration_worker/main.py"),
        )

    def test_all_workers_use_monotonic_lease_windows(self):
        paths = (
            "apps/ai-worker/src/testing_agent_ai_worker/worker/runner.py",
            "apps/api-ui-worker/src/test_worker/poller/task_poller.py",
            "apps/perf-worker/src/testing_agent_perf_worker/worker/lease.py",
            "apps/integration-worker/src/testing_agent_integration_worker/domain/execution.py",
            "apps/integration-worker/src/testing_agent_integration_worker/worker/lease.py",
        )
        for path in paths:
            self.assertIn("time.monotonic", source(path), path)
        self.assertIn(
            "lease_seconds // 2",
            source("apps/ai-worker/src/testing_agent_ai_worker/worker/lifecycle.py"),
        )
        for path in (
            "apps/perf-worker/src/testing_agent_perf_worker/worker/poller.py",
            "apps/integration-worker/src/testing_agent_integration_worker/worker/lease.py",
        ):
            self.assertIn("lease_seconds / 3", source(path), path)
        self.assertIn(
            "DEFAULT_LEASE_SECONDS = 30.0",
            source("apps/api-ui-worker/src/test_worker/poller/task_poller.py"),
        )

    def test_status_vocabularies_match_documented_protocols(self):
        ai = source("apps/ai-worker/src/testing_agent_ai_worker/models/execution.py")
        for value in ("success", "failed", "error", "canceled"):
            self.assertIn(f'"{value}"', ai)
        self.assertNotIn(
            "TaskStatus.CANCELED",
            source("apps/ai-worker/src/testing_agent_ai_worker/worker/runner.py"),
        )
        self.assertIn(
            'Literal["error", "canceled"]',
            source("apps/api-ui-worker/src/test_worker/poller/task_poller.py"),
        )
        perf = source("apps/perf-worker/src/testing_agent_perf_worker/contracts/result.py")
        for value in ("completed", "failed", "stopped", "canceled"):
            self.assertIn(f'"{value}"', perf)
        self.assertIn(
            'Literal["succeeded", "failed", "unknown"]',
            source("apps/integration-worker/src/testing_agent_integration_worker/schemas/step.py"),
        )

    def test_protocol_identity_and_lease_fields_match_the_contract(self):
        ai = source("apps/ai-worker/src/testing_agent_ai_worker/platform/schemas.py")
        self.assertIn('AliasChoices("leaseSeconds", "lease_seconds")', ai)
        self.assertIn(
            '"workerId"',
            source("apps/ai-worker/src/testing_agent_ai_worker/platform/result_sink.py"),
        )
        api = source(
            "apps/api-ui-worker/src/test_worker/control_plane/client.py"
        ) + source("apps/api-ui-worker/src/test_worker/contracts/parsing.py")
        for field in ('"taskId"', '"workerId"', '"leaseSeconds"', '"stopRequested"', '"heartbeatAt"'):
            self.assertIn(field, api)
        perf = source("apps/perf-worker/src/testing_agent_perf_worker/contracts/spec.py") + source(
            "apps/perf-worker/src/testing_agent_perf_worker/contracts/worker.py"
        )
        self.assertIn("alias_generator=to_camel", perf)
        for field in ("lease_seconds", "stop_requested", "worker_id"):
            self.assertIn(field, perf)
        integration = source(
            "apps/integration-worker/src/testing_agent_integration_worker/schemas/job.py"
        )
        self.assertIn("alias_generator=to_camel", integration)
        for field in ("lease_seconds", "worker_id", "claim_generation", "runtime_generation"):
            self.assertIn(field, integration)

    def test_shutdown_and_lease_loss_mapping_is_explicit(self):
        self.assertIn(
            "task lease lost, result discarded",
            source("apps/ai-worker/src/testing_agent_ai_worker/worker/runner.py"),
        )
        api = source("apps/api-ui-worker/src/test_worker/poller/task_poller.py")
        self.assertIn('status="canceled"', api)
        self.assertIn("ExecutionLeaseLost", api)
        perf = source("apps/perf-worker/src/testing_agent_perf_worker/worker/poller.py")
        self.assertIn("RunStatus.CANCELED", perf)
        self.assertIn("RunStatus.STOPPED", perf)
        integration = source(
            "apps/integration-worker/src/testing_agent_integration_worker/services/step_execution.py"
        )
        self.assertIn('error_code="lease_lost"', integration)
        self.assertIn('status = "unknown" if uncertain else "failed"', integration)


if __name__ == "__main__":
    unittest.main()
