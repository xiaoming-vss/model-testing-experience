import html
import re
from typing import Any

from testing_agent_integration_worker.core.errors import PreflightError
from testing_agent_integration_worker.domain.bug_description import (
    canonical,
    native_file_metadata,
    native_image_url,
    source_hash,
    unresolved_legacy_images,
)
from testing_agent_integration_worker.schemas.job import JobInput


async def description_input(gateway, view: JobInput) -> tuple[dict[str, Any], str]:
    frozen, target = view.snapshot["description"], view.snapshot["target"]
    remote_id = view.mapping["remoteBugId"]
    remote = await gateway.bug(
        remote_id,
        target,
        view.mapping.get("productId") or view.snapshot["existingPayload"].get("productID"),
    )
    data: dict[str, Any] = {"remoteBugId": remote_id}
    before = remote.get("steps")
    if frozen["previousStatus"] == "unknown":
        previous = frozen["previous"]
        desired = previous.get("desiredSteps", "")
        if (
            isinstance(before, str)
            and desired
            and not unresolved_legacy_images(before)
            and canonical(before, target["instanceUrl"])
            == canonical(desired, target["instanceUrl"])
        ):
            return {
                **data,
                "beforeSteps": before,
                "result": {"descriptionHash": source_hash(desired)},
            }, "noop"
        if (
            not isinstance(before, str)
            or previous.get("repairAttempted")
            or view.snapshot["source"]["html"] != previous.get("sourceHtml")
            or not unresolved_legacy_images(before)
            or not unresolved_legacy_images(desired)
            or canonical(before, target["instanceUrl"], legacy_encoded=True)
            != canonical(desired, target["instanceUrl"], legacy_encoded=True)
        ):
            raise PreflightError(
                "baseline_changed", "Unknown description requires read-only recovery"
            )
    if not frozen["images"] and frozen["previousStatus"] == "none":
        return data, "noop"
    remote_files = remote.get("files", {})
    if isinstance(remote_files, dict):
        remote_files = list(remote_files.values())
    if not isinstance(remote_files, list):
        raise PreflightError("remote_unavailable", "Remote image metadata is unavailable")
    by_id = {str(value.get("id")): value for value in remote_files if isinstance(value, dict)}
    paths, extensions = {}, {}
    for file_id in frozen["images"]:
        record = view.mapping.get("files", {}).get(file_id, {})
        uploaded = by_id.get(str(record.get("remoteFileId")))
        if uploaded is None:
            identifier = record.get("remoteFileId")
            if type(identifier) is not int or identifier <= 0:
                raise PreflightError(
                    "dependency_failed", "Required image has no confirmed remote file"
                )
            uploaded = await gateway.file_info(remote_id, identifier)
        uploaded = native_file_metadata(
            uploaded,
            target["instanceUrl"],
            remote_id,
            [before, frozen.get("expectedSteps"), frozen.get("previous", {}).get("desiredSteps")],
        )
        paths[file_id] = native_image_url(uploaded, target["instanceUrl"], remote_id)
        extensions[file_id] = uploaded["extension"]

    def replace(match):
        identifier = re.search(r'data-file-id=["\']([^"\']+)["\']', match[0])
        if identifier is None or identifier[1] not in paths:
            raise PreflightError("input_changed", "Description image references are invalid")
        return f'<img src="{html.escape(paths[identifier[1]], quote=True)}" >'

    desired = re.sub(r"<img\b[^>]*>", replace, view.snapshot["source"]["html"], flags=re.IGNORECASE)
    if not isinstance(before, str):
        raise PreflightError("remote_unavailable", "Remote description is unavailable")
    baseline = frozen["expectedSteps"] or view.snapshot["createPayload"]["steps"]
    if frozen["previousStatus"] != "unknown":
        # Supplement images only; preserve the legacy guard against replacing text.
        plain_local = re.sub(r"<img\b[^>]*>", "", view.snapshot["source"]["html"], flags=re.I)
        plain_base = re.sub(r"<img\b[^>]*>", "", baseline, flags=re.I).replace("[图片未同步]", "")
        plain_local = re.sub(r"<p>\s*</p>", "", plain_local)
        plain_base = re.sub(r"<p>\s*</p>", "", plain_base)
        if canonical(plain_local) != canonical(plain_base):
            raise PreflightError(
                "baseline_changed",
                "Description text changed; reconcile before supplementing images",
            )
    if frozen["previousStatus"] != "unknown" and canonical(
        before, target["instanceUrl"]
    ) != canonical(baseline, target["instanceUrl"]):
        raise PreflightError("baseline_changed", "Description baseline was edited externally")
    data.update(
        beforeSteps=before, desiredSteps=desired, imagePaths=paths, imageExtensions=extensions
    )
    if not unresolved_legacy_images(before) and canonical(
        before, target["instanceUrl"]
    ) == canonical(desired, target["instanceUrl"]):
        data["result"] = {"descriptionHash": source_hash(desired)}
        return data, "noop"
    return data, "write"
