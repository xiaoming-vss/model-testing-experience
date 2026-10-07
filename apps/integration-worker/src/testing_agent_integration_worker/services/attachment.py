from typing import Any

from testing_agent_integration_worker.schemas.job import JobInput, JobStep


async def attachment_input(gateway, view: JobInput, step: JobStep) -> tuple[dict[str, Any], str]:
    remote_id = view.mapping["remoteBugId"]
    await gateway.bug(
        remote_id,
        view.snapshot["target"],
        view.mapping.get("productId") or view.snapshot["existingPayload"].get("productID"),
    )
    file_id = step.step_key.split(":", 1)[1]
    data = {"remoteBugId": remote_id, "fileId": file_id}
    existing = view.mapping.get("files", {}).get(file_id)
    if existing:
        data["result"] = {"remoteFileId": existing["remoteFileId"]}
        return data, "noop"
    return data, "write"
