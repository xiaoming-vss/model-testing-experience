"""Local domain reservations and receipts; every method shares the queue transaction."""

import html
import re
from datetime import UTC, datetime

from testing_agent.domain.integration_execution import require
from testing_agent.domain.zentao_fields import FIELD_UPDATE_KEY as KEY
from testing_agent.domain.zentao_fields import fields_equal as equal
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.repositories.integration_bug_state import IntegrationBugStateRepository
from testing_agent.schemas.integration_job import IntegrationRemoteResult
from testing_agent.services.bug_zentao_description import (
    canonical,
    native_image_url,
    source_hash,
    unresolved_legacy_images,
)
from testing_agent.services.integration_bug_state import IntegrationBugState
from testing_agent.services.integration_recovery import record_verified_recovery
from testing_agent.services.service_instance import instance_key


class IntegrationBugSteps:
    def __init__(self, session, *, context=None, authorization=None):
        self.context = context
        self.authorization = authorization
        self.session = session
        self.repository = IntegrationBugStateRepository(session)
        self.state = IntegrationBugState(session, record_recovery=record_verified_recovery)

    def render(self, job, data) -> str:
        paths = data.get("imagePaths", {})
        extensions = data.get("imageExtensions", {})
        images = job.snapshot_json["description"]["images"]
        require(isinstance(paths, dict) and set(paths) == set(images), "正文图片映射不完整")
        references = {}
        for identifier in images:
            mapping = job.mapping_json.get("files", {}).get(identifier, {})
            require(bool(mapping.get("remoteFileId")), "正文图片尚未上传成功")
            extension = extensions.get(identifier)
            require(extension in {"png", "jpg", "jpeg"}, "正文图片格式不支持")
            path = native_image_url(
                {
                    "id": mapping["remoteFileId"],
                    "objectType": "bug",
                    "objectID": job.mapping_json["remoteBugId"],
                    "extension": extension,
                    "url": paths[identifier],
                },
                job.snapshot_json["target"]["instanceUrl"],
                job.mapping_json["remoteBugId"],
            )
            require(path == paths[identifier], "图片路径不是原生读取路由")
            references[identifier] = f'<img src="{html.escape(path, quote=True)}" >'

        def replace(match):
            identifier = re.search(r'data-file-id=["\']([^"\']+)["\']', match[0])
            require(identifier is not None and identifier[1] in references, "正文图片引用已变化")
            assert identifier is not None
            return references[identifier[1]]

        return re.sub(
            r"<img\b[^>]*>", replace, job.snapshot_json["source"]["html"], flags=re.IGNORECASE
        )

    async def validate(self, job, step, body):
        assert self.context is not None and self.authorization is not None
        _, row, _, _, _ = await self.context.current(job)
        authority = await self.authorization.authority(job)
        require(authority.access_revision == body.access_revision, "本人授权或 MCP 访问材料已变化")
        data = body.input
        if body.decision == "failed":
            result = IntegrationRemoteResult.model_validate(data.get("result", {}))
            require(result.error_code is not None, "前置失败必须说明安全错误代码")
            return
        if step.kind == "create_bug":
            remote_id = job.mapping_json.get("remoteBugId")
            if body.decision == "noop":
                require(
                    bool(remote_id) and data.get("result", {}).get("remoteBugId") == remote_id,
                    "尚未关联 Bug，不能跳过创建",
                )
                return
            require(not remote_id, "已关联的 Bug 不能再次创建")
            payload = data.get("payload", {})
            require(
                isinstance(payload, dict)
                and {k: v for k, v in payload.items() if k != "productID"}
                == job.snapshot_json["createPayload"],
                "创建输入不属于冻结快照",
            )
            require(
                type(payload.get("productID")) is int and payload["productID"] > 0,
                "创建缺少有效禅道产品编号",
            )
            require(row is None or row.status in {"failed", "preparing"}, "原 Bug 创建结果未核对")
        elif step.kind == "upload_attachment":
            file_id = step.step_key.split(":", 1)[1]
            require(
                data.get("fileId") == file_id
                and data.get("remoteBugId") == job.mapping_json.get("remoteBugId"),
                "上传步骤目标不属于本任务",
            )
            existing = job.mapping_json.get("files", {}).get(file_id)
            if body.decision == "noop":
                require(
                    bool(existing)
                    and data.get("result", {}).get("remoteFileId") == existing["remoteFileId"],
                    "附件尚无成功映射，不能跳过上传",
                )
                return
            require(not existing, "已成功附件不能重复上传")
            record = await self.repository.attachment(job.bug_id, file_id)
            require(await self.context.retryable_attachment(record), "原附件结果未核对或正在执行")
        elif step.kind == "update_fields":
            expected, desired = job.snapshot_json["before"], job.snapshot_json["desired"]
            require(
                data.get("remoteBugId") == job.mapping_json.get("remoteBugId")
                and data.get("before") == expected,
                "字段旧值与本次预览不一致",
            )
            changes = {
                k: v
                for k, v in desired.items()
                if (set(v) != set(expected[k]) if k == "openedBuild" else v != expected[k])
            }
            require(data.get("payload") == changes, "字段修改只允许提交有变化的指定字段")
            require((not changes) == (body.decision == "noop"), "字段无变化时禁止远端写入")
            if body.decision == "noop":
                actual = data.get("result", {})
                require(equal(actual, desired), "无变化核对结果不一致")
        else:
            await self.validate_description(job, row, body)

    async def validate_description(self, job, row, body):
        data = body.input
        frozen = job.snapshot_json["description"]
        require(data.get("remoteBugId") == job.mapping_json.get("remoteBugId"), "正文目标已变化")
        previous = frozen["previous"]
        instance = job.snapshot_json["target"]["instanceUrl"]
        if frozen["previousStatus"] == "unknown" and body.decision == "noop":
            before = data.get("beforeSteps")
            original_desired = previous.get("desiredSteps", "")
            require(
                row.description_operation_id == frozen["previousOperationId"]
                and isinstance(before, str)
                and bool(original_desired)
                and not unresolved_legacy_images(before)
                and canonical(before, instance) == canonical(original_desired, instance),
                "未知正文只允许核对已确认到达的原内容",
            )
            require(
                data.get("result", {}).get("descriptionHash") == source_hash(original_desired),
                "未知正文核对摘要不一致",
            )
            return
        if not frozen["images"] and frozen["previousStatus"] == "none":
            require(body.decision == "noop", "没有正文图片，不需要额外描述写入")
            return
        desired = self.render(job, data)
        require(data.get("desiredSteps") == desired, "正文转换不属于冻结源内容与文件映射")
        before = data.get("beforeSteps")
        require(isinstance(before, str), "正文更新缺少远端基线")
        if frozen["previousStatus"] == "unknown":
            require(
                row.description_operation_id == frozen["previousOperationId"],
                "待核对正文操作已变化",
            )
            if body.decision == "noop":
                require(
                    not unresolved_legacy_images(before)
                    and canonical(before, instance)
                    == canonical(previous.get("desiredSteps", ""), instance),
                    "未知正文只允许核对已确认到达的原内容",
                )
                return
            legacy = previous.get("desiredSteps", "")
            require(
                job.snapshot_json["source"]["html"] == previous.get("sourceHtml")
                and not previous.get("repairAttempted")
                and unresolved_legacy_images(before)
                and unresolved_legacy_images(legacy)
                and canonical(before, instance, legacy_encoded=True)
                == canonical(legacy, instance, legacy_encoded=True),
                "未知正文不得重复写入，只有已证实的旧图片编码错误允许一次修复",
            )
        else:
            # 正文漂移按平台内容覆盖禅道（ADR 0006 账本机制不变），覆盖事实由 Worker 记录。
            require(
                (canonical(before, instance) == canonical(desired, instance))
                == (body.decision == "noop"),
                "正文无变化时禁止写入",
            )
        if body.decision == "noop":
            require(
                data.get("result", {}).get("descriptionHash") == source_hash(desired),
                "正文核对摘要不一致",
            )

    async def reserve(self, job, step):
        data, snapshot = step.input_json, job.snapshot_json
        now = datetime.now(UTC)
        row = await self.repository.push(job.bug_id)
        if step.kind == "create_bug":
            if row is None:
                row = BugZentaoPush(bug_id=job.bug_id)
                self.session.add(row)
            row.operation_id, row.actor_user_id = step.operation_id, job.actor_user_id
            row.service_id, row.instance_url = job.service_id, snapshot["target"]["instanceUrl"]
            row.instance_key = instance_key(snapshot["target"]["instanceUrl"])
            row.status, row.remote_bug_id = "creating", None
            row.target_json, row.payload_json = snapshot["target"], data["payload"]
            row.error_message = ""
            job.mapping_json = {**job.mapping_json, "pushOperationId": step.operation_id}
        elif step.kind == "upload_attachment":
            file_id = data["fileId"]
            file = next(f for f in snapshot["source"]["files"] if f["fileId"] == file_id)
            attachment = await self.repository.attachment(job.bug_id, file_id)
            if attachment is None:
                attachment = BugZentaoAttachment(bug_id=job.bug_id, file_id=file_id)
                self.session.add(attachment)
            attachment.sha256 = file["sha256"]
            attachment.instance_url = snapshot["target"]["instanceUrl"]
            attachment.remote_bug_id = job.mapping_json["remoteBugId"]
            attachment.remote_file_id = None
            attachment.operation_id, attachment.actor_user_id = step.operation_id, job.actor_user_id
            attachment.status, attachment.error_message = "uploading", ""
        elif step.kind == "update_fields":
            assert row is not None  # Validated under the same project/step transaction.
            row.payload_json = {
                **row.payload_json,
                KEY: {
                    "operationId": step.operation_id,
                    "actorUserId": job.actor_user_id,
                    "status": "updating",
                    "before": snapshot["before"],
                    "desired": snapshot["desired"],
                    "error": "",
                },
            }
        else:
            assert row is not None  # Validated under the same project/step transaction.
            if snapshot["description"]["previousStatus"] == "unknown":
                # validate_description already proved the original legacy write reached its
                # baseline before granting the single bounded encoding repair.
                row.description_status = "succeeded"
                await record_verified_recovery(
                    self.session,
                    job.bug_id,
                    snapshot["description"]["previousOperationId"],
                    "update_description",
                    IntegrationRemoteResult(
                        description_hash=source_hash(
                            snapshot["description"]["previous"]["desiredSteps"]
                        )
                    ),
                    actor=job.actor_user_id,
                )
            row.description_operation_id = step.operation_id
            row.description_status, row.description_updated_at = "syncing", now
            row.description_sync_json = {
                "sourceHtml": snapshot["source"]["html"],
                "sourceHash": snapshot["description"]["sourceHash"],
                "expectedSteps": data["beforeSteps"],
                "desiredSteps": data["desiredSteps"],
                "remoteBugId": job.mapping_json["remoteBugId"],
                "instanceUrl": snapshot["target"]["instanceUrl"],
                "actorUserId": job.actor_user_id,
                "repairAttempted": snapshot["description"]["previousStatus"] == "unknown",
                "overwrote": data.get("overwrote", {}),
            }

    async def apply(self, job, step, evidence):
        await self.state.apply(job, step, evidence)

    async def sync(self, job):
        await self.state.sync(job)
