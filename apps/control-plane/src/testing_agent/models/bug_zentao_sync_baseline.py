"""Per-field-group sync baseline: the reference for three-way reverse comparison."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class BugZentaoSyncBaseline(Base):
    """每个 Bug 每个字段组只保留一行：最近一次确认同步时两端的内容快照。

    反向拉取用它做三方比对（基线 / 本地当前 / 远端当前），判断远端变化、
    本地领先还是双端冲突；导入成功时以「本地等于导入时刻远端」初始化。
    """

    __tablename__ = "bug_zentao_sync_baselines"
    __table_args__ = (
        UniqueConstraint("bug_id", "field_group", name="uk_bug_zentao_baseline"),
        {"comment": "Bug 禅道反向同步的字段组基线：最近一次确认应用时两端值快照"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    bug_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bugs.bug_id", ondelete="CASCADE"),
        comment="平台 Bug 业务标识",
    )
    field_group: Mapped[str] = mapped_column(
        String(20),
        comment="字段组标识：profile 基本信息 / description 描述 / status 状态 / assignee 责任人",
    )
    local_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="应用确认时刻的本地字段组值快照 JSON"
    )
    remote_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="应用确认时刻的远端字段组值快照 JSON"
    )
    operation_id: Mapped[str] = mapped_column(
        String(64), comment="本轮确认应用的操作标识，用于结果核对与去重"
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime, comment="基线确认应用时间（UTC）")
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
