from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from html import unescape
from re import I as _RE_I
from re import finditer as _re_finditer
from re import search as _re_search
from re import sub as _re_sub
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select

from testing_agent.core.errors import AppError
from testing_agent.domain import zentao_bug_mapping as mapping
from testing_agent.domain.rich_text import has_rich_text_content, sanitize_rich_text
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_sync_baseline import BugZentaoSyncBaseline
from testing_agent.repositories.bug import BugRepository
from testing_agent.services.bug_import.contracts import BugImportResult
from testing_agent.services.bug_zentao_description import image_id
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
        图片按 R41 记待处理，不冒充完整同步。图片引用与推送侧共用同一套识别。
        """
        steps = str(detail.get("steps") or "")
        instance = access.base_url
        catalog = _attachment_index(detail.get("attachments"))
        targets: dict[int, dict] = dict(catalog)
        image_refs = _image_refs(steps, instance)
        for rid in image_refs:
            targets.setdefault(rid, catalog.get(rid, {}))
        file_map: dict[int, str] = {}
        failures: list[str] = []
        pulled_count = 0
        for rid, meta in sorted(targets.items()):
            local_file_id, error = await self._pull_one(
                client, access, user_id, project_id, bug_id, remote_bug_id, rid, operation_id, meta
            )
            if local_file_id is None:
                failures.append(_file_label(rid, meta, error or "拉取失败"))
                continue
            file_map[rid] = local_file_id
            pulled_count += 1
        rewritten, resolved, foreign_images = _rewrite_images(steps, file_map, instance)
        # 非禅道文件的图片按平台富文本规则剔除（R45）；说明始终保留，不随描述组完成而消失。
        foreign_note = _foreign_image_note(foreign_images) if foreign_images else ""
        notes = [*failures, *([foreign_note] if foreign_note else [])]
        clean = sanitize_rich_text(rewritten) if rewritten else ""
        bug = await self.repository.get_bug(bug_id)
        if bug is None:
            return
        complete = (
            bool(image_refs)
            and bool(clean)
            and has_rich_text_content(clean)
            and all(rid in file_map for rid in image_refs)
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
        for note in failures:
            result["pending"].append({"field": "description", "reason": note})
        if complete and "description" in {item["field"] for item in result["pending"]}:
            result["pending"] = [
                item for item in result["pending"] if item["field"] != "description"
            ]
        if foreign_note:
            result["pending"].append({"field": "description", "reason": foreign_note})

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
_SRC_ATTR = r"\ssrc=(\"[^\"]*\"|'[^']*')"


def _file_number(source: str, instance: str) -> int | None:
    """禅道文件编号；不是禅道文件引用的图片来源返回 None（R44）。"""
    identifier = image_id(source, instance) if source else None
    if identifier and identifier.isdigit() and int(identifier) > 0:
        return int(identifier)
    return None


def _tag_source(tag: str) -> str:
    """img 标签的 src 原值，实体已解码；HTML 里 `&` 通常写作 `&amp;`。"""
    found = _re_search(_SRC_ATTR, tag, _RE_I)
    return unescape(found[1][1:-1]) if found else ""


def _image_refs(raw_html: str, instance: str) -> list[int]:
    """正文图片引用的禅道文件编号，按出现顺序去重（R44）。"""
    refs: list[int] = []
    seen: set[int] = set()
    for match in _re_finditer(_IMG_TAG, raw_html or "", _RE_I):
        rid = _file_number(_tag_source(match.group(0)), instance)
        if rid is not None and rid not in seen:
            refs.append(rid)
            seen.add(rid)
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


def _rewrite_images(
    raw_html: str, file_map: dict[int, str], instance: str
) -> tuple[str, list[int], list[str]]:
    """把已拉取的禅道图片改写为平台 data-file-id，其余图片按平台富文本规则剔除。

    拉取失败的图片已由文件管线记待处理；无法识别的图片来源原样返回，
    由调用方说明（R41/R45），不静默丢弃。
    """
    resolved: list[int] = []
    foreign: list[str] = []

    def repl(match):
        tag = match.group(0)
        source = _tag_source(tag)
        rid = _file_number(source, instance)
        if rid is None:
            foreign.append(source)
        elif rid in file_map:
            resolved.append(rid)
            return _re_sub(_SRC_ATTR, f' data-file-id="{file_map[rid]}"', tag, count=1)
        return ""

    return _re_sub(_IMG_TAG, repl, raw_html or "", flags=_RE_I), resolved, foreign


def _foreign_image_note(sources: list[str]) -> str:
    """说明被剔除的非禅道文件图片；只带主机与路径，不带查询串（R45）。"""
    labels = list(dict.fromkeys(_image_label(source) for source in sources))
    shown = "、".join(labels[:3])
    return f"正文有 {len(sources)} 处图片不是禅道文件，未导入：{shown}" + (
        " 等" if len(labels) > 3 else ""
    )


def _image_label(source: str) -> str:
    try:
        url = urlsplit(source)
    except ValueError:
        return "地址格式无效"
    if url.scheme or url.hostname:
        return f"{url.scheme}://{url.hostname}{url.path}"[:120]
    return source[:120]


def _file_label(remote_file_id: int, meta: dict, message: str) -> str:
    title = meta.get("title") or f"#{remote_file_id}"
    return f"文件 {title}（#{remote_file_id}）待处理：{message}"


def get_pull_error(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return str(exc)


def _digest(text: str) -> str:
    return sha256((text or "").encode()).hexdigest()
