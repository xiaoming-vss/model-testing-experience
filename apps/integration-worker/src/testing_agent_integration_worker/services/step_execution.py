import asyncio
import logging
import time
from typing import Any, Literal
from uuid import uuid4

from testing_agent_integration_worker.core.errors import (
    ControlPlaneError,
    LeaseLost,
    WriteUncertain,
)
from testing_agent_integration_worker.domain.bug_description import (
    canonical,
    source_hash,
    unresolved_legacy_images,
)
from testing_agent_integration_worker.domain.bug_fields import equal, fields
from testing_agent_integration_worker.domain.execution import Execution
from testing_agent_integration_worker.gateways.mcp import McpCallError
from testing_agent_integration_worker.repositories.evidence import Evidence
from testing_agent_integration_worker.schemas.job import Access, JobInput, JobStep
from testing_agent_integration_worker.schemas.step import RemoteResult, ResultEvent

logger = logging.getLogger(__name__)


class StepExecution:
    def __init__(self, control_plane, gateway_factory, evidence, *, progress=lambda: None):
        self.control_plane = control_plane
        self.gateway_factory = gateway_factory
        self.evidence = evidence
        self.progress = progress

    async def replay_evidence(self) -> None:
        for item in list(self.evidence.items.values()):
            self.progress()
            try:
                await self.control_plane.result(
                    item.job_id, item.step_key, item.event, evidence=True
                )
                self.evidence.acknowledge(item.event.event_id)
            except ControlPlaneError as error:
                logger.info(
                    "Evidence pending job=%s step=%s status=%s",
                    item.job_id,
                    item.step_key,
                    error.status,
                )

    async def report(self, item: Evidence) -> dict[str, Any]:
        self.evidence.record(item)
        try:
            response = await self.control_plane.result(item.job_id, item.step_key, item.event)
        except ControlPlaneError as error:
            if error.status not in {403, 404, 409}:
                raise
            response = await self.control_plane.result(
                item.job_id, item.step_key, item.event, evidence=True
            )
        self.evidence.acknowledge(item.event.event_id)
        return response

    async def fail_before_write(self, execution: Execution, step: JobStep, code: str) -> None:
        if not execution.window.active():
            raise LeaseLost()
        await self.control_plane.failure(
            execution.claim.job_id,
            step.step_key,
            {
                **execution.claim.identity().model_dump(by_alias=True),
                "eventId": uuid4().hex,
                "errorCode": code,
            },
        )

    async def readback(
        self, gateway, view: JobInput, step: JobStep, data: dict[str, Any]
    ) -> RemoteResult:
        target = view.snapshot["target"]
        await gateway.verify_instance(target)
        remote = await gateway.bug(
            view.mapping["remoteBugId"],
            target,
            view.mapping.get("productId") or view.snapshot["existingPayload"].get("productID"),
        )
        if step.kind == "update_fields":
            actual = fields(remote)
            return RemoteResult(
                opened_build=actual["openedBuild"],
                assigned_to=actual["assignedTo"],
                error_code=None if equal(actual, view.snapshot["desired"]) else "remote_rejected",
            )
        before = remote.get("steps")
        desired = data["desiredSteps"]
        if (
            not isinstance(before, str)
            or unresolved_legacy_images(before)
            or canonical(before, target["instanceUrl"]) != canonical(desired, target["instanceUrl"])
        ):
            raise WriteUncertain("Remote description did not confirm the prepared content")
        return RemoteResult(description_hash=source_hash(desired))

    async def execute(
        self,
        execution: Execution,
        view: JobInput,
        step: JobStep,
        access: Access,
        data: dict[str, Any],
        *,
        decision="write",
    ) -> bool:
        if not execution.window.active():
            raise LeaseLost()
        started = time.monotonic()
        permit = await self.control_plane.prepare(
            view.job_id,
            step.step_key,
            {
                **execution.claim.identity().model_dump(by_alias=True),
                "prepareRequestId": uuid4().hex,
                "inputRevision": view.input_revision,
                "targetRevision": view.target_revision,
                "accessRevision": access.access_revision,
                "input": data,
                "decision": decision,
            },
        )
        if not permit.write_allowed and permit.status in {"noop", "succeeded", "failed", "blocked"}:
            return permit.job_status in {None, "claimed", "running"} and permit.status != "failed"
        status: Literal["succeeded", "failed", "unknown"] = "unknown"
        outcome = RemoteResult(error_code="remote_uncertain")
        wrote = False
        write_confirmed = False
        remote_started = None
        if permit.write_allowed:
            if permit.access is None or permit.operation is None or permit.permit_seconds is None:
                raise WriteUncertain("Write permit has no validated execution material")
            deadline = min(
                execution.window.deadline, started + permit.permit_seconds - execution.window.margin
            )
            try:
                async with self.gateway_factory(permit.access) as gateway:
                    await gateway.verify_instance(view.snapshot["target"])
                    if not execution.window.active() or time.monotonic() >= deadline:
                        raise LeaseLost()
                    wrote = True
                    remote_started = time.monotonic()
                    async with asyncio.timeout(permit.operation.timeout_seconds):
                        outcome = await gateway.write(permit.operation)
                        write_confirmed = True
                        if step.kind in {"update_description", "update_fields"}:
                            outcome = await self.readback(gateway, view, step, data)
                    status = "failed" if outcome.error_code == "remote_rejected" else "succeeded"
            except McpCallError as error:
                uncertain = write_confirmed or error.uncertain
                status = "unknown" if uncertain else "failed"
                outcome = RemoteResult(
                    error_code="remote_uncertain" if uncertain else "remote_rejected"
                )
            except LeaseLost:
                outcome = RemoteResult(error_code="lease_lost")
            except (TimeoutError, WriteUncertain):
                outcome = RemoteResult(error_code="remote_uncertain")
            except asyncio.CancelledError:
                # A canceled HTTP await does not establish that the external write was not applied.
                outcome = RemoteResult(error_code="remote_uncertain" if wrote else "lease_lost")
            except Exception:
                status = "unknown" if wrote else "failed"
                outcome = RemoteResult(
                    error_code="remote_uncertain" if wrote else "remote_unavailable"
                )
        event = ResultEvent(
            **execution.claim.identity().model_dump(),
            event_id=uuid4().hex,
            operation_id=permit.operation_id,
            status=status,
            result=outcome,
            remote_duration_ms=round((time.monotonic() - remote_started) * 1000)
            if remote_started is not None
            else None,
        )
        logger.info(
            "Remote step job=%s step=%s operation=%s service=%s status=%s remote_ms=%s error=%s",
            view.job_id,
            step.step_key,
            permit.operation_id,
            view.snapshot["target"].get("mcpServiceId", ""),
            status,
            event.remote_duration_ms,
            outcome.error_code or "",
        )
        response = await self.report(
            Evidence(job_id=view.job_id, step_key=step.step_key, event=event)
        )
        return response.get("jobStatus") in {"claimed", "running"}
