"""Adapt independent executions to the existing AI Worker claim contract."""

import json
from copy import deepcopy
from typing import Any

from testing_agent.domain.ai_execution_format import FIELDS
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.stage_storage.authorization import DirectWorkerAuthority
from testing_agent.services.stage_storage.payload import worker_payloads
from testing_agent.services.standalone_worker_authorization import StandaloneWorkerAuthority


def standalone_worker_payloads(
    authority: StandaloneWorkerAuthority, queue: WorkerTask, *, lease_seconds: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Expose the dispatched attempt as Worker runId and the frozen input as payload."""
    dispatched = authority.dispatched_attempt
    frozen = deepcopy(dispatched.input_snapshot_json or {})
    if dispatched.revision_instruction:
        config = frozen.get("config")
        current = frozen.get("currentOutput")
        if isinstance(config, dict) and isinstance(current, str) and current:
            field = FIELDS.get(authority.current_stage.stage, "resultYaml")
            if field != "resultYaml":
                try:
                    config[field] = json.loads(current)
                except ValueError:
                    config[field] = current
            else:
                config[field] = current
    direct = DirectWorkerAuthority(
        stage_id=authority.current_stage.id,
        attempt_id=dispatched.id,
        actor_id=authority.actor_id,
        task=authority.task,
        input_snapshot=frozen,
        revision_instruction=dispatched.revision_instruction,
    )
    claim, snapshot = worker_payloads(
        direct, queue, stage_name=authority.current_stage.stage, lease_seconds=lease_seconds
    )
    claim["checkpointEnabled"] = bool(authority.execution.checkpoint_enabled)
    snapshot["checkpointEnabled"] = bool(authority.execution.checkpoint_enabled)
    return claim, snapshot
