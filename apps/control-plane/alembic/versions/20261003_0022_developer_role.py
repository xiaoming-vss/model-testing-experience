"""Allow project developers with Bug-only access."""

import sqlalchemy as sa

from alembic import op

revision = "20261003_0022"
down_revision = "20260927_0021"
branch_labels = None
depends_on = None


def _roles(expression: str) -> None:
    with op.batch_alter_table("project_members") as batch:
        batch.drop_constraint(op.f("ck_project_members_project_member_role"), type_="check")
        batch.create_check_constraint("project_member_role", expression)


def upgrade() -> None:
    _roles("role IN ('member', 'viewer', 'developer')")


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM project_members WHERE role='developer'"))
        .scalar()
    ):
        raise RuntimeError("仍有开发成员，请先调整项目角色后再降级")
    _roles("role IN ('member', 'viewer')")
