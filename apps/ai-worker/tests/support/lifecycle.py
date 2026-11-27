"""Shared worker lifecycle factory for runner tests."""

from testing_agent_ai_worker.worker.lifecycle import WorkerLifecycle


def lifecycle(**overrides) -> WorkerLifecycle:
    values = {
        "poll_interval_seconds": 10,
        "heartbeat_interval_seconds": 60,
        "run_once": False,
    }
    values.update(overrides)
    return WorkerLifecycle(**values)
