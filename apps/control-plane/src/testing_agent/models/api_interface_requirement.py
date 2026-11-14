from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk


class ApiInterfaceRequirement(Base):
    __tablename__ = "api_interface_requirements"
    __table_args__ = (
        UniqueConstraint("interface_id", "requirement_id", name="uk_api_interface_requirement"),
        Index("idx_api_interface_requirement_req", "requirement_id", "interface_id"),
        {"comment": "接口定义与需求的可选多对多关联"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    interface_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "api_interfaces.interface_id",
            name="fk_api_interface_requirements_interface",
            ondelete="CASCADE",
        ),
        nullable=False,
        comment="接口定义业务标识",
    )
    requirement_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "requirements.requirement_id",
            name="fk_api_interface_requirements_requirement",
            ondelete="CASCADE",
        ),
        nullable=False,
        comment="需求业务标识",
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="关联创建时间（UTC）")
