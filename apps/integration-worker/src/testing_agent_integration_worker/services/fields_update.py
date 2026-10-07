from testing_agent_integration_worker.core.errors import PreflightError
from testing_agent_integration_worker.domain.bug_fields import changes, equal, fields


async def fields_input(gateway, view):
    target = view.snapshot["target"]
    product = await gateway.verify_target(target)
    remote = await gateway.bug(view.mapping["remoteBugId"], target, product)
    before = fields(remote)
    if not equal(before, view.snapshot["before"]):
        raise PreflightError("baseline_changed", "Remote field values changed after the preview")
    payload = changes(before, view.snapshot["desired"])
    data = {"remoteBugId": view.mapping["remoteBugId"], "before": before, "payload": payload}
    if not payload:
        data["result"] = before
        return data, "noop"
    await gateway.validate_choices(target, product, payload)
    if not equal(fields(await gateway.bug(view.mapping["remoteBugId"], target, product)), before):
        raise PreflightError("baseline_changed", "Remote fields changed during validation")
    return data, "write"
