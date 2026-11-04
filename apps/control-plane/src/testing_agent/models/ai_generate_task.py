from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class AiGenerateTask(Base):
    __tablename__ = "ai_generate_tasks"
    __table_args__ = (
        Index("idx_ai_task_project_type_created", "project_id", "task_type", "created_at", "id"),
        Index("ix_ai_generate_tasks_project_id", "project_id"),
        Index("ix_ai_generate_tasks_sprint_id", "sprint_id"),
        Index("ix_ai_generate_tasks_requirement_id", "requirement_id"),
        Index("ix_ai_generate_tasks_order_id", "order_id"),
        Index("ix_ai_generate_tasks_creator_user_id", "creator_user_id"),
        {"comment": "AI 生成与分析任务定义；候选结果经审核导入后才成为正式测试资产"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    task_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="任务业务标识"
    )
    task_type: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False, default="api_case_generate", comment="任务类型"
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="AI 任务名称")
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "projects.project_id", name="fk_ai_generate_tasks_project_id", ondelete="RESTRICT"
        ),
        nullable=False,
        comment="项目业务标识",
    )
    sprint_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="迭代业务标识")
    requirement_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="需求业务标识")
    # 非需求域任务（测试报告、测试图谱）以其他业务实体为锚点，测试图谱锚在测试单上。
    order_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        comment="测试单图谱任务的锚点测试单标识；其他任务通常为空字符串",
    )
    creator_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="任务创建者用户业务标识"
    )
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="AI 任务输入来源类型"
    )
    source_content: Mapped[str] = mapped_column(
        LONGTEXT, nullable=False, comment="AI 任务源输入内容"
    )
    instruction: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="AI 任务补充生成指令"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
