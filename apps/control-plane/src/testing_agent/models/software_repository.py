from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class SoftwareRepository(Base):
    if TYPE_CHECKING:
        # 列表聚合计数；由 repository 批量写入，不对应表字段。
        interface_count: int

    __tablename__ = "software_repositories"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uk_software_repository_project_name"),
        Index("idx_software_repository_project_name", "project_id", "name"),
        {"comment": "项目级软件仓库：固定对应一个 Git 仓库、base path 与接口定义"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    software_repository_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="软件仓库业务标识"
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "projects.project_id",
            name="fk_software_repositories_project",
            ondelete="RESTRICT",
        ),
        nullable=False,
        comment="所属项目业务标识",
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="软件仓库名称，同一项目内唯一"
    )
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="软件仓库用途说明"
    )
    base_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="",
        comment="软件仓库级 URL 路径前缀；空字符串表示无前缀",
    )
    interface_groups_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="手工创建的接口分组名列表；空分组也保留",
    )
    repository_project_id: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        comment="关联 GitLab 仓库的远端项目标识",
    )
    repository_group_id: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        comment="软件仓库所选 GitLab 群组的标识快照",
    )
    repository_instance_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        comment="GitLab 实例地址摘要；用于匹配操作者同实例个人授权",
    )
    repository_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="",
        comment="GitLab 仓库完整命名空间路径快照，例如 commerce/order-service",
    )
    repository_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", comment="GitLab 仓库名称快照"
    )
    repository_instance_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="",
        comment="GitLab 实例规范化地址；不包含凭据",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="乐观并发版本；软件仓库信息每次更新加一",
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="创建软件仓库的用户业务标识，仅用于追溯，不代表私有归属",
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
