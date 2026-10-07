from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk


class BugActivity(Base):
    """Bug 处理记录与动态：状态流转、转派、评论、字段修改、附件补充。

    多轮修复、回归、拒绝和重新打开的记录全部保留，不覆盖历史。
    """

    __tablename__ = "bug_activities"
    __table_args__ = {"comment": "Bug 处理记录与动态；保留历次流转、编辑、转派、评论和附件操作"}
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    activity_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="Bug 动态业务标识"
    )
    bug_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bugs.bug_id", name="fk_bug_activities_bug_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="平台 Bug 业务标识",
    )
    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Bug 动态类型：status_change/transfer/comment/edit/attachment",
    )
    actor_user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        comment="执行 Bug 动作的用户业务标识",
    )
    action: Mapped[str] = mapped_column(
        String(30), nullable=False, default="", comment="Bug 处理动作"
    )
    from_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", comment="动作前 Bug 状态"
    )
    to_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", comment="动作后 Bug 状态"
    )
    # 修复说明、回归结果、拒绝/重开原因、评论等文本内容。
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="Bug 动态正文")
    # 字段前后变化、拒绝原因取值、附件清单等结构化补充。
    detail_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, comment="Bug 动作详细变更 JSON"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")

    @property
    def detail(self) -> dict[str, Any]:
        return self.detail_json or {}
