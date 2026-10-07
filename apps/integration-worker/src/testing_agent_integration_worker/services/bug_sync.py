import logging

from testing_agent_integration_worker.core.errors import (
    ControlPlaneError,
    LeaseLost,
    PreflightError,
)
from testing_agent_integration_worker.domain.execution import Execution
from testing_agent_integration_worker.gateways.mcp import McpCallError
from testing_agent_integration_worker.services.attachment import attachment_input
from testing_agent_integration_worker.services.description import description_input
from testing_agent_integration_worker.services.fields_update import fields_input

logger = logging.getLogger(__name__)


class BugWorkflow:
    def __init__(self, control_plane, gateway_factory, step_execution):
        self.control_plane, self.gateway_factory = control_plane, gateway_factory
        self.steps = step_execution

    async def run(self, execution: Execution) -> None:
        claim = execution.claim
        while execution.window.active():
            try:
                view = await self.control_plane.input(claim.job_id, claim.identity())
            except ControlPlaneError as error:
                if error.status in {403, 404, 409}:
                    return
                raise
            pending = next(
                (
                    step
                    for step in view.steps
                    if step.status == "pending"
                    and all(
                        next(s for s in view.steps if s.step_key == dependency).status
                        in {"succeeded", "noop"}
                        for dependency in step.dependencies
                    )
                ),
                None,
            )
            if pending is None:
                await self.control_plane.completed(claim.job_id, claim.identity())
                return
            access = await self.control_plane.access(claim.job_id, claim.identity())
            try:
                async with self.gateway_factory(access) as gateway:
                    target = view.snapshot["target"]
                    await gateway.verify_instance(target)
                    if pending.kind == "create_bug":
                        if view.mapping.get("remoteBugId"):
                            await gateway.bug(
                                view.mapping["remoteBugId"],
                                target,
                                view.snapshot["existingPayload"].get("productID"),
                            )
                            data, decision = (
                                {"result": {"remoteBugId": view.mapping["remoteBugId"]}},
                                "noop",
                            )
                        else:
                            product = await gateway.verify_target(target)
                            payload = {**view.snapshot["createPayload"], "productID": product}
                            await gateway.validate_choices(target, product, payload)
                            data, decision = {"payload": payload}, "write"
                    elif pending.kind == "upload_attachment":
                        data, decision = await attachment_input(gateway, view, pending)
                    elif pending.kind == "update_description":
                        data, decision = await description_input(gateway, view)
                    else:
                        data, decision = await fields_input(gateway, view)
                if not await self.steps.execute(
                    execution, view, pending, access, data, decision=decision
                ):
                    return
            except PreflightError as error:
                await self.steps.fail_before_write(execution, pending, error.code)
            except McpCallError:
                await self.steps.fail_before_write(execution, pending, "remote_unavailable")
            except ControlPlaneError as error:
                if error.status == 409:
                    await self.steps.fail_before_write(execution, pending, "input_changed")
                else:
                    raise
            except LeaseLost:
                return
            except Exception as error:
                logger.warning(
                    "Preflight stopped job=%s step=%s error=%s",
                    claim.job_id,
                    pending.step_key,
                    type(error).__name__,
                )
                await self.steps.fail_before_write(execution, pending, "remote_unavailable")
