from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class RequirementSoftwareRepository(Base):
    __tablename__ = "requirement_software_repositories"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id",
            "software_repository_id",
            name="uk_requirement_software_repository",
        ),
        Index(
            "idx_requirement_software_repository_repo",
            "software_repository_id",
            "requirement_id",
        ),
        {"comment": "需求与软件仓库的多对多关联及需求级工作分支、基线分支"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    requirement_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "requirements.requirement_id",
            name="fk_requirement_software_repositories_requirement",
            ondelete="CASCADE",
        ),
        nullable=False,
        comment="需求业务标识",
    )
    software_repository_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "software_repositories.software_repository_id",
            name="fk_requirement_software_repositories_repository",
            ondelete="RESTRICT",
        ),
        nullable=False,
        comment="软件仓库业务标识",
    )
    branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        comment="本次需求使用的工作分支；换绑仓库后为空，需重新填写",
    )
    baseline_branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        comment="代码风险分析的基线分支；换绑仓库后为空，需重新填写",
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="关联创建人用户业务标识"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
