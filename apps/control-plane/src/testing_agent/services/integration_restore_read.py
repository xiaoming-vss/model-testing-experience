"""Readonly MCP proof for a restored Bug; this module has no database or write tools."""

import html
import re

from testing_agent.core.errors import AppError
from testing_agent.domain.rich_text import extract_file_ids
from testing_agent.services.bug_zentao_attachment import UPLOAD_TIMEOUT
from testing_agent.services.bug_zentao_description import (
    canonical,
    native_file_metadata,
    native_image_url,
    source_hash,
)
from testing_agent.services.bug_zentao_fields import equal, fields
from testing_agent.services.bug_zentao_push import remote_id
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_mcp_instance import discover_instance


def require(condition, message):
    if not condition:
        raise AppError(409, message, 409)


def render(value, native):
    def replace(match):
        tag = match[0]
        identifiers = extract_file_ids(tag)
        if not identifiers:
            return tag
        require(len(identifiers) == 1 and identifiers[0] in native, "恢复正文缺少已核对的图片附件")
        tag = re.sub(r"\s+data-file-id\s*=\s*([\"']).*?\1", "", tag, flags=re.I)
        tag = re.sub(r"\s+src\s*=\s*([\"']).*?\1", "", tag, flags=re.I)
        return re.sub(
            r"\s*/?>$", ' src="' + html.escape(native[identifiers[0]], quote=True) + '">', tag
        )

    return re.sub(r"<img\b[^>]*>", replace, value, flags=re.I)


async def read_restore_proof(pushes, context, request):
    """All data in context is copied before entering this read-only network phase."""
    access, packet, target = context["access"], context["packet"], context["target"]
    token = access.token.get_secret_value()
    identity = await discover_instance(access.endpoint, token, client_factory=pushes.client_factory)
    require(
        instance_key(identity["instanceUrl"]) == instance_key(target["instanceUrl"]),
        "MCP 实例与恢复目标不一致",
    )
    current = packet["push"]
    identifier = request.remote_bug_id
    if current and current.get("remote_bug_id"):
        require(current["remote_bug_id"] == identifier, "恢复编号与当前关联不一致")
    require(
        set(request.files).issubset({f["file_id"] for f in packet["files"]}),
        "恢复附件编号不属于当前 Bug",
    )
    require(
        all(type(value) is int and value > 0 for value in request.files.values()),
        "恢复附件编号不合法",
    )
    async with pushes.client_factory(access.endpoint, token) as client:
        product = await pushes.verify_target(client, target)
        bug = (await client.call("get_bugs_bugID", {"bugID": identifier})).get("bug", {})
        require(
            remote_id(bug.get("id")) == identifier
            and str(bug.get("deleted", "0")).lower() not in {"1", "true", "yes", "on"}
            and all(str(bug.get(k)) == str(target[k]) for k in ("project", "execution", "story"))
            and str(bug.get("product")) == str(product),
            "恢复对象不存在或实例、产品、层级不匹配",
        )
        if not current or current["status"] != "succeeded":
            titles = {
                job["snapshot_json"].get("createPayload", {}).get("title")
                for job in packet["jobs"]
                if job["task_type"] == "zentao_bug_sync"
            }
            if current:
                titles.add(current["payload_json"].get("title"))
            elif packet["attachments"]:
                titles.add(packet["bug"]["title"])
            titles.discard(None)
            require(
                titles and all(title == bug.get("title") for title in titles),
                "恢复对象标题与原创建输入不一致",
            )
        actual = fields(bug)
        if current:
            previous = current["payload_json"].get("_fieldUpdate", {})
            if previous.get("status") in {"preparing", "updating", "unknown"}:
                require(
                    equal(actual, previous.get("desired", {})), "原字段写入仍未确认，继续保持隔离"
                )
        for job in packet["jobs"]:
            previous_mapping = job["mapping_json"]
            require(
                not previous_mapping.get("remoteBugId")
                or previous_mapping["remoteBugId"] == identifier,
                "原任务远端关联不同，请单独隔离历史操作",
            )
            if current and previous_mapping.get("pushOperationId"):
                require(
                    current["operation_id"] == previous_mapping["pushOperationId"],
                    "原任务关联操作已变化，请单独隔离历史操作",
                )
            require(
                job["target_key"] == context["target_key"], "原任务实例已变化，请单独隔离历史操作"
            )
            previous_target = job["snapshot_json"].get("target", {})
            require(
                all(previous_target.get(k) == target[k] for k in ("project", "execution", "story")),
                "原任务层级已变化，请单独隔离历史操作",
            )
            if job["task_type"] == "zentao_bug_fields_update":
                require(
                    equal(actual, job["snapshot_json"].get("desired", {})),
                    "原字段任务结果尚未确认，继续保持隔离",
                )
        remote_files = bug.get("files", {})
        if isinstance(remote_files, dict):
            remote_files = list(remote_files.values())
        require(isinstance(remote_files, list), "远端附件列表不完整")
        records = {f["file_id"]: f for f in packet["attachments"]}
        proofs, native = {}, {}
        for file in packet["files"]:
            old = records.get(file["file_id"])
            remote_file = request.files.get(file["file_id"])
            if old and old.get("remote_file_id"):
                require(
                    not remote_file or remote_file == old["remote_file_id"],
                    "附件编号与原关联不一致",
                )
                remote_file = old["remote_file_id"]
            require(remote_file is not None, "请提供待恢复文件的远端编号，不能按名称猜测")
            detail = next((f for f in remote_files if str(f.get("id")) == str(remote_file)), None)
            if detail is None:
                detail = (await client.call("get_files_fileID", {"fileID": remote_file})).get(
                    "file"
                )
            require(detail is not None, "远端文件不属于目标 Bug")
            assert detail is not None
            require(
                str(detail.get("id")) == str(remote_file)
                and detail.get("objectType") == "bug"
                and str(detail.get("objectID")) == str(identifier)
                and str(detail.get("deleted", "0")).lower() not in {"1", "true", "yes", "on"},
                "远端文件归属不匹配或已删除",
            )
            proof = await client.call(
                "get_bug_attachment",
                {"bugId": identifier, "fileId": remote_file},
                timeout=UPLOAD_TIMEOUT,
            )
            require(
                str(proof.get("id")) == str(remote_file)
                and proof.get("sha256") == file["sha256"]
                and proof.get("size") == file["size"]
                and proof.get("status") == "success"
                and not proof.get("uncertain"),
                "远端附件字节与恢复文件不一致",
            )
            proofs[file["file_id"]] = {
                "remoteFileId": remote_file,
                "sha256": file["sha256"],
                "size": file["size"],
            }
            if file["file_id"] in extract_file_ids(packet["bug"]["description_html"]):
                detail = native_file_metadata(
                    detail,
                    target["instanceUrl"],
                    identifier,
                    [
                        bug.get("steps"),
                        current["description_sync_json"].get("desiredSteps") if current else None,
                    ],
                )
                native[file["file_id"]] = native_image_url(
                    detail, target["instanceUrl"], identifier
                )
            else:
                # Frozen task HTML may still reference a file omitted from current HTML.
                needed = any(
                    file["file_id"]
                    in extract_file_ids(
                        j["snapshot_json"].get("description", {}).get("sourceHtml", "")
                    )
                    for j in packet["jobs"]
                )
                if needed and str(detail.get("extension", "")).lower() in {"png", "jpg", "jpeg"}:
                    detail = native_file_metadata(
                        detail,
                        target["instanceUrl"],
                        identifier,
                        [
                            bug.get("steps"),
                            current["description_sync_json"].get("desiredSteps")
                            if current
                            else None,
                        ],
                    )
                    native[file["file_id"]] = native_image_url(
                        detail, target["instanceUrl"], identifier
                    )
        candidates = [packet["bug"]["description_html"]]
        candidates.extend(
            job["snapshot_json"].get("description", {}).get("sourceHtml", "")
            for job in packet["jobs"]
            if job["task_type"] == "zentao_bug_sync"
        )
        description = None
        for candidate in candidates:
            if set(extract_file_ids(candidate)).issubset(native):
                expected = render(candidate, native)
                if canonical(expected, target["instanceUrl"]) == canonical(
                    bug.get("steps", ""), target["instanceUrl"]
                ):
                    description = {
                        "sourceHtml": candidate,
                        "sourceHash": source_hash(candidate),
                        "desiredSteps": expected,
                    }
                    break
        if current and current["description_status"] in {"preparing", "syncing", "unknown"}:
            require(
                isinstance(current["description_sync_json"].get("desiredSteps"), str),
                "原正文缺少写入证据，继续保持隔离",
            )
            require(
                canonical(bug.get("steps", ""), target["instanceUrl"])
                == canonical(
                    current["description_sync_json"].get("desiredSteps", ""), target["instanceUrl"]
                ),
                "原正文写入结果尚未确认，继续保持隔离",
            )
        if description is None and current and current["description_status"] == "succeeded":
            previous = current["description_sync_json"]
            expected = previous.get("desiredSteps")
            if isinstance(expected, str) and canonical(
                expected, target["instanceUrl"]
            ) == canonical(bug.get("steps", ""), target["instanceUrl"]):
                description = {
                    "sourceHtml": previous.get("sourceHtml", ""),
                    "sourceHash": previous.get("sourceHash", ""),
                    "desiredSteps": expected,
                }
        require(description is not None, "远端正文与已保存的源内容不一致，继续保持隔离")
        assert description is not None
        if current:
            original = current["description_sync_json"].get("desiredSteps")
            if isinstance(original, str) and canonical(
                original, target["instanceUrl"]
            ) == canonical(description["desiredSteps"], target["instanceUrl"]):
                # Equivalent HTML does not change the bytes of an existing operation's proof.
                description["desiredSteps"] = original
        return {
            "remoteBugId": identifier,
            "productId": product,
            "fields": actual,
            "files": proofs,
            "description": description,
        }
