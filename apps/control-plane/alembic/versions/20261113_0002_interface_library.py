"""interface library: project apps, interface definitions and requirement links

Revision ID: 20261113_0002
Revises: 20261103_0001
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20261113_0002"
down_revision = "20261103_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_apps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="数据库内部主键"),
        sa.Column("app_id", sa.String(length=64), nullable=False, comment="接口应用业务标识"),
        sa.Column("project_id", sa.String(length=64), nullable=False, comment="所属项目业务标识"),
        sa.Column(
            "name", sa.String(length=100), nullable=False, comment="应用名称，同一项目内唯一"
        ),
        sa.Column(
            "description",
            sa.String(length=512),
            nullable=False,
            comment="应用用途说明",
        ),
        sa.Column(
            "base_path",
            sa.String(length=512),
            nullable=False,
            comment="应用级 URL 路径前缀；空字符串表示无前缀",
        ),
        sa.Column(
            "repository_project_id",
            sa.String(length=120),
            nullable=False,
            comment="关联 GitLab 仓库的远端项目标识；空字符串表示未关联",
        ),
        sa.Column(
            "repository_path",
            sa.String(length=512),
            nullable=False,
            comment="GitLab 仓库完整命名空间路径快照，例如 commerce/order-service",
        ),
        sa.Column(
            "repository_name",
            sa.String(length=255),
            nullable=False,
            comment="GitLab 仓库名称快照",
        ),
        sa.Column(
            "repository_instance_url",
            sa.String(length=512),
            nullable=False,
            comment="GitLab 实例规范化地址；不包含凭据",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            comment="应用是否启用；不影响所属接口的独立状态",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            comment="乐观并发版本；应用信息每次更新加一",
        ),
        sa.Column(
            "created_by_user_id",
            sa.String(length=64),
            nullable=False,
            comment="创建应用的用户业务标识，仅用于追溯，不代表应用私有归属",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="记录创建时间（UTC）",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="记录最后更新时间（UTC）",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_api_apps_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_apps")),
        sa.UniqueConstraint("app_id", name=op.f("uq_api_apps_app_id")),
        sa.UniqueConstraint("project_id", "name", name="uk_api_app_project_name"),
        comment="项目级接口应用及可选代码仓库、base path 配置",
    )
    op.create_index(
        "idx_api_app_project_enabled",
        "api_apps",
        ["project_id", "enabled", "name"],
        unique=False,
    )
    op.create_table(
        "api_interfaces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="数据库内部主键"),
        sa.Column(
            "interface_id",
            sa.String(length=64),
            nullable=False,
            comment="接口定义业务标识",
        ),
        sa.Column(
            "app_id",
            sa.String(length=64),
            nullable=False,
            comment="所属接口应用业务标识",
        ),
        sa.Column(
            "name",
            sa.String(length=120),
            nullable=False,
            comment="接口名称，同一应用内不要求唯一",
        ),
        sa.Column(
            "method",
            sa.String(length=10),
            nullable=False,
            comment="规范化大写 HTTP 方法",
        ),
        sa.Column(
            "path",
            sa.String(length=1024),
            nullable=False,
            comment="规范化相对路径，不包含应用 base path",
        ),
        sa.Column(
            "path_key",
            sa.String(length=64),
            nullable=False,
            comment="规范化路径的 SHA-256 十六进制摘要，用于身份唯一约束",
        ),
        sa.Column(
            "description",
            sa.String(length=1024),
            nullable=False,
            comment="接口用途、调用约束等说明",
        ),
        sa.Column(
            "tags_json",
            mysql.JSON(),
            nullable=False,
            comment="标签字符串数组，导入和手工维护",
        ),
        sa.Column(
            "headers_json",
            mysql.JSON(),
            nullable=False,
            comment="请求头定义数组",
        ),
        sa.Column(
            "path_params_json",
            mysql.JSON(),
            nullable=False,
            comment="Path 参数定义数组",
        ),
        sa.Column(
            "query_params_json",
            mysql.JSON(),
            nullable=False,
            comment="Query 参数定义数组",
        ),
        sa.Column(
            "body_type",
            sa.String(length=20),
            nullable=False,
            comment="请求体类型：none/json/form/raw",
        ),
        sa.Column(
            "body_schema_json",
            mysql.JSON(),
            nullable=True,
            comment="请求体 JSON Schema；无 schema 时为空",
        ),
        sa.Column(
            "body_example_json",
            mysql.JSON(),
            nullable=True,
            comment="请求体示例 JSON 值；无示例时为空",
        ),
        sa.Column(
            "body_text",
            sa.Text(),
            nullable=False,
            comment="Raw 请求体文本；仅 body_type=raw 时使用",
        ),
        sa.Column(
            "response_status",
            sa.Integer(),
            nullable=False,
            comment="默认成功响应状态码",
        ),
        sa.Column(
            "response_description",
            sa.String(length=512),
            nullable=False,
            comment="默认成功响应说明",
        ),
        sa.Column(
            "response_schema_json",
            mysql.JSON(),
            nullable=True,
            comment="响应 JSON Schema；无 schema 时为空",
        ),
        sa.Column(
            "response_example_json",
            mysql.JSON(),
            nullable=True,
            comment="响应示例 JSON 值；无示例时为空",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            comment="接口是否启用；与应用状态独立",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            comment="乐观并发版本；接口内容或状态每次更新加一",
        ),
        sa.Column(
            "source_type",
            sa.String(length=20),
            nullable=False,
            comment="来源类型：manual/openapi_file；openapi_url 预留，本期不写入",
        ),
        sa.Column(
            "source_name",
            sa.String(length=255),
            nullable=False,
            comment="来源文档标题或文件名；手工创建为空",
        ),
        sa.Column(
            "source_url",
            sa.String(length=1024),
            nullable=False,
            comment="来源文档地址；本期恒为空，后续 URL 导入启用",
        ),
        sa.Column(
            "source_version",
            sa.String(length=64),
            nullable=False,
            comment="来源文档 info.version",
        ),
        sa.Column(
            "source_imported_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近一次由文档导入覆盖的时间（UTC）；手工创建为空",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="记录创建时间（UTC）",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="记录最后更新时间（UTC）",
        ),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["api_apps.app_id"],
            name="fk_api_interfaces_app",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_interfaces")),
        sa.UniqueConstraint("interface_id", name=op.f("uq_api_interfaces_interface_id")),
        sa.UniqueConstraint(
            "app_id",
            "method",
            "path_key",
            name="uk_api_interface_app_method_path",
        ),
        comment="项目接口定义及请求、响应结构",
    )
    op.create_index(
        "idx_api_interface_app_updated",
        "api_interfaces",
        ["app_id", "updated_at", "id"],
        unique=False,
    )
    op.create_index(
        "idx_api_interface_updated",
        "api_interfaces",
        ["updated_at", "id"],
        unique=False,
    )
    op.create_index(
        "idx_api_interface_method",
        "api_interfaces",
        ["method"],
        unique=False,
    )
    op.create_table(
        "api_interface_requirements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="数据库内部主键"),
        sa.Column(
            "interface_id",
            sa.String(length=64),
            nullable=False,
            comment="接口定义业务标识",
        ),
        sa.Column(
            "requirement_id",
            sa.String(length=64),
            nullable=False,
            comment="需求业务标识",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="关联创建时间（UTC）",
        ),
        sa.ForeignKeyConstraint(
            ["interface_id"],
            ["api_interfaces.interface_id"],
            name="fk_api_interface_requirements_interface",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.requirement_id"],
            name="fk_api_interface_requirements_requirement",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_interface_requirements")),
        sa.UniqueConstraint(
            "interface_id",
            "requirement_id",
            name="uk_api_interface_requirement",
        ),
        comment="接口定义与需求的可选多对多关联",
    )
    op.create_index(
        "idx_api_interface_requirement_req",
        "api_interface_requirements",
        ["requirement_id", "interface_id"],
        unique=False,
    )


def downgrade() -> None:
    # The explicit index backs the requirement FK; MySQL refuses to drop it while the FK
    # exists. Dropping the table removes its indexes and constraints together.
    op.drop_table("api_interface_requirements")
    op.drop_index("idx_api_interface_method", table_name="api_interfaces")
    op.drop_index("idx_api_interface_updated", table_name="api_interfaces")
    op.drop_index("idx_api_interface_app_updated", table_name="api_interfaces")
    op.drop_table("api_interfaces")
    op.drop_index("idx_api_app_project_enabled", table_name="api_apps")
    op.drop_table("api_apps")
