from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class UiElementGroup(Base):
    __tablename__ = "ui_element_groups"
    __table_args__ = (
        UniqueConstraint(
            "software_repository_id", "kind", "route_key", name="uk_ui_element_group_route"
        ),
        {"comment": "前端应用的页面和公共元素分组"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    group_id: Mapped[str] = mapped_column(String(64), unique=True, comment="元素分组业务标识")
    software_repository_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "software_repositories.software_repository_id",
            name="fk_ui_element_groups_repository",
            ondelete="RESTRICT",
        ),
        comment="所属前端应用的软件仓库业务标识",
    )
    kind: Mapped[str] = mapped_column(String(10), comment="分组类型：page/common")
    name: Mapped[str] = mapped_column(String(120), comment="元素分组显示名称")
    route_template: Mapped[str] = mapped_column(
        String(512), comment="页面路由模板；公共组使用空字符串"
    )
    route_key: Mapped[str] = mapped_column(
        String(64), comment="路由模板的 SHA-256 摘要，参与同仓库分组查重"
    )
    created_by_user_id: Mapped[str] = mapped_column(String(64), comment="创建分组的用户业务标识")
    created_at: Mapped[CreatedAt] = mapped_column(comment="分组创建时间（UTC）")


class UiElement(Base):
    __tablename__ = "ui_elements"
    __table_args__ = (
        UniqueConstraint("group_id", "locator_key", name="uk_ui_element_locator"),
        Index("idx_ui_element_group_updated", "group_id", "updated_at", "id"),
        {"comment": "可复用 UI 元素及其固定定位或参数模板"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    element_id: Mapped[str] = mapped_column(String(64), unique=True, comment="元素库条目业务标识")
    group_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ui_element_groups.group_id", name="fk_ui_elements_group", ondelete="RESTRICT"),
        comment="所属页面或公共分组业务标识",
    )
    name: Mapped[str] = mapped_column(String(120), comment="元素显示名称")
    scope: Mapped[str] = mapped_column(String(255), comment="元素所在容器或可用的页面状态")
    locator_type: Mapped[str] = mapped_column(String(20), comment="UI 执行器定位方式")
    locator_value: Mapped[str] = mapped_column(Text, comment="固定的定位值或含命名参数的定位模板")
    parameters_json: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, comment="定位参数定义数组；每项含 name 和 description，固定定位为空数组"
    )
    locator_key: Mapped[str] = mapped_column(
        String(64), comment="作用范围、定位方式和模板的 SHA-256 摘要，参与分组内查重"
    )
    verification_status: Mapped[str] = mapped_column(
        String(16),
        default="pending",
        comment="定位验证状态：pending/verified；手工修改定位后待验证",
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, comment="元素乐观并发版本，每次内容更新加一"
    )
    created_by_user_id: Mapped[str] = mapped_column(String(64), comment="创建元素的用户业务标识")
    created_at: Mapped[CreatedAt] = mapped_column(comment="元素创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="元素更新时间（UTC）")

    @property
    def parameterized(self) -> bool:
        return bool(self.parameters_json)
