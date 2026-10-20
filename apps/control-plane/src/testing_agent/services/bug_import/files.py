from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from re import I as _RE_I
from re import finditer as _re_finditer
from re import search as _re_search
from re import sub as _re_sub
from typing import Any

from sqlalchemy import select

from testing_agent.core.errors import AppError
from testing_agent.domain import zentao_bug_mapping as mapping
from testing_agent.domain.rich_text import has_rich_text_content, sanitize_rich_text
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_sync_baseline import BugZentaoSyncBaseline
from testing_agent.repositories.bug import BugRepository
from testing_agent.services.bug_import.contracts import BugImportResult
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.stored_file import StoredFileService
from testing_agent.services.zentao_mcp import ZentaoMcpConnection


class BugImportFiles:
    def __init__(
        self, repository: BugRepository, files: StoredFileService, *, id_factory: Callable[[], str]
    ) -> None:
        self.repository = repository
        self.session = repository.session
        self.files = files
        self.new_id = id_factory

    async def pull(
        self,
        client: McpClient,
        access: ZentaoMcpConnection,
        user_id: str,
        project_id: str,
        bug_id: str,
        remote_bug_id: int,
        detail: dict[str, Any],
        operation_id: str,
        result: BugImportResult,
    ) -> None:
        """拉取远端附件与正文图片（R44-R47），重写正文并按完成度写描述基线。

        只认远端附件清单内、属于本 Bug 的文件；正文里无法解析或拉取失败的
        图片按 R41 记待处理，不冒充完整同步。
        """
        steps = str(detail.get("steps") or "")
        catalog = _attachment_index(detail.get("attachments"))
        targets: dict[int, dict] = dict(catalog)
        for rid in _image_refs(steps):
            targets.setdefault(rid, catalog.get(rid, {}))
        file_map: dict[int, str] = {}
        notes: list[str] = []
        pulled_count = 0
        for rid, meta in sorted(targets.items()):
            local_file_id, error = await self._pull_one(
                client, access, user_id, project_id, bug_id, remote_bug_id, rid, operation_id, meta
            )
            if local_file_id is None:
                notes.append(_file_label(rid, meta, error or "拉取失败"))
                continue
            file_map[rid] = local_file_id
            pulled_count += 1
        rewritten, resolved = _rewrite_images(steps, file_map)
        clean = sanitize_rich_text(rewritten) if rewritten else ""
        bug = await self.repository.get_bug(bug_id)
        if bug is None:
            return
        complete = (
            bool(_image_refs(steps))
            and bool(clean)
            and has_rich_text_content(clean)
            and not [rid for rid in _image_refs(steps) if rid not in file_map]
        )
        if clean and clean != bug.description_html and (resolved or has_rich_text_content(clean)):
            bug.description_html = clean
        if complete:
            baseline = await self.session.scalar(
                select(BugZentaoSyncBaseline).where(
                    BugZentaoSyncBaseline.bug_id == bug_id,
                    BugZentaoSyncBaseline.field_group == "description",
                )
            )
            if baseline is None:
                # 本地摘要按应用后的正文计算，远端摘要按当前远端净化文本计算：
                # 两侧表示形式不同，基线记录"本轮确认时各自的样子"（R32）。
                self.session.add(
                    BugZentaoSyncBaseline(
                        bug_id=bug_id,
                        field_group="description",
                        local_snapshot_json={"digest": _digest(clean)},
                        remote_snapshot_json={
                            "digest": mapping.remote_description(steps)["digest"]
                        },
                        operation_id=operation_id,
                        applied_at=datetime.now(UTC),
                    )
                )
        self.session.add(
            BugActivity(
                activity_id=self.new_id(),
                bug_id=bug_id,
                kind="sync",
                actor_user_id=user_id,
                action="zentao_files",
                content=f"从禅道拉取文件：成功 {pulled_count} 个，待处理 {len(notes)} 个",
                detail_json={
                    "operationId": operation_id,
                    "remoteBugId": remote_bug_id,
                    "pulled": pulled_count,
                    "notes": notes,
                },
            )
        )
        await self.repository.commit()
        for note in notes:
            result["pending"].append({"field": "description", "reason": note})
        if complete and "description" in {item["field"] for item in result["pending"]}:
            result["pending"] = [
                item for item in result["pending"] if not item["field"] == "description"
            ]

    async def _pull_one(
        self,
        client,
        access,
        user_id: str,
        project_id: str,
        bug_id: str,
        remote_bug_id: int,
        remote_file_id: int,
        operation_id: str,
        meta: dict,
    ) -> tuple[str | None, str | None]:
        """单个远端文件：元数据核对 → 平台票据 → MCP 回传内容 → 校验入库。"""
        try:
            metadata = await client.call(
                "get_bug_attachment", {"bugId": remote_bug_id, "fileId": remote_file_id}
            )
            if metadata.get("status") != "success":
                raise McpCallError("禅道附件核对失败")
            filename = str(
                metadata.get("filename") or meta.get("title") or f"file-{remote_file_id}"
            )
            size = int(metadata.get("size") or 0)
            sha256 = str(metadata.get("sha256") or "")
            if size <= 0 or len(sha256) != 64:
                raise McpCallError("禅道附件元数据不完整")
            upload = await self.files.initiate_pull(
                user_id,
                project_id,
                bug_id=bug_id,
                filename=filename,
                size=size,
                sha256=sha256,
            )
            file_id = upload["fileId"]
        except (AppError, McpCallError) as exc:
            message = get_pull_error(exc)
            await self._record_pull(
                bug_id,
                "",
                access,
                remote_bug_id,
                remote_file_id,
                operation_id,
                user_id,
                "failed",
                message,
            )
            return None, message
        try:
            transfer = await client.call(
                "get_bug_attachment",
                {"bugId": remote_bug_id, "fileId": remote_file_id, "uploadUrl": upload["upload"]},
            )
            if transfer.get("status") != "success" or not transfer.get("uploaded"):
                raise McpCallError("禅道附件内容回传未完成")
            await self.files.complete(user_id, file_id)
            await self.files.attach(
                user_id, file_id, project_id, "bug", bug_id, purpose="attachment"
            )
        except (AppError, McpCallError) as exc:
            message = get_pull_error(exc)
            await self._record_pull(
                bug_id,
                file_id,
                access,
                remote_bug_id,
                remote_file_id,
                operation_id,
                user_id,
                "failed",
                message,
            )
            return None, message
        await self._record_pull(
            bug_id,
            file_id,
            access,
            remote_bug_id,
            remote_file_id,
            operation_id,
            user_id,
            "succeeded",
            "",
        )
        return file_id, None

    async def _record_pull(
        self,
        bug_id: str,
        file_id: str,
        access,
        remote_bug_id: int,
        remote_file_id: int,
        operation_id: str,
        user_id: str,
        status: str,
        message: str,
    ) -> None:
        if not file_id:
            # 尚无本地文件行的失败只进待处理清单，重试由反向拉取完成（R56）。
            return
        self.session.add(
            BugZentaoAttachment(
                bug_id=bug_id,
                file_id=file_id,
                sha256="",
                instance_url=access.base_url,
                remote_bug_id=remote_bug_id,
                remote_file_id=remote_file_id,
                operation_id=operation_id,
                direction="pull",
                actor_user_id=user_id,
                status=status,
                error_message=message,
            )
        )
        await self.repository.commit()


_IMG_TAG = r"<img\b[^>]*/?>"
_FILE_REF = r"file-read-(\d+)"
_SRC_ATTR = r"\ssrc=(\"[^\"]*\"|'[^']*')"


def _search_file_ref(tag: str) -> int | None:
    match = _re_search(_FILE_REF, tag, _RE_I)
    return int(match.group(1)) if match else None


def _image_refs(raw_html: str) -> list[int]:
    """正文图片引用的禅道文件编号，按出现顺序去重（R44）。"""
    refs: list[int] = []
    for match in _re_finditer(_FILE_REF, raw_html or "", _RE_I):
        rid = int(match.group(1))
        if rid not in refs:
            refs.append(rid)
    return refs


def _attachment_index(raw: object) -> dict[int, dict]:
    """远端附件清单规范化为 {编号: {title, size}}；形状异常按空处理（R44）。"""
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list):
        return {}
    index: dict[int, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        if identifier is None:
            continue
        try:
            rid = int(identifier)
        except (TypeError, ValueError):
            continue
        if rid > 0:
            index[rid] = {"title": str(item.get("title") or ""), "size": item.get("size") or 0}
    return index


def _rewrite_images(raw_html: str, mapping: dict[int, str]) -> tuple[str, list[int]]:
    """把已解析图片的禅道地址改写为平台 data-file-id；未解析图片剔除并返回清单。"""
    resolved: list[int] = []

    def repl(match):
        tag = match.group(0)
        found = _re_search(_FILE_REF, tag, _RE_I)
        if found is None:
            return ""
        local = mapping.get(int(found.group(1)))
        if local is None:
            return ""
        resolved.append(int(found.group(1)))
        return _re_sub(_SRC_ATTR, f' data-file-id="{local}"', tag, count=1)

    return _re_sub(_IMG_TAG, repl, raw_html or "", flags=_RE_I), resolved


def _file_label(remote_file_id: int, meta: dict, message: str) -> str:
    title = meta.get("title") or f"#{remote_file_id}"
    return f"文件 {title}（#{remote_file_id}）待处理：{message}"


def get_pull_error(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return str(exc)


def _digest(text: str) -> str:
    return sha256((text or "").encode()).hexdigest()
