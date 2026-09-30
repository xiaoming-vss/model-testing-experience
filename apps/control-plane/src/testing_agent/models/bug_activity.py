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
    id: Mapped[IdPk]
    activity_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    bug_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bugs.bug_id", name="fk_bug_activities_bug_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    from_status: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    to_status: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    # 修复说明、回归结果、拒绝/重开原因、评论等文本内容。
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 字段前后变化、拒绝原因取值、附件清单等结构化补充。
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[CreatedAt]

    @property
    def detail(self) -> dict[str, Any]:
        return self.detail_json or {}
