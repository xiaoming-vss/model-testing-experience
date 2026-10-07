"""Allow multiple MCP services and retain the original service on legacy bindings."""

import json

import sqlalchemy as sa

from alembic import op

revision = "20261004_0027"
down_revision = "20261004_0026"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    metadata = sa.MetaData()
    services = sa.Table("shared_services", metadata, autoload_with=connection)
    auth = sa.Table("service_authorizations", metadata, autoload_with=connection)
    bindings = sa.Table("resource_bindings", metadata, autoload_with=connection)
    sprints = sa.Table("sprints", metadata, autoload_with=connection)
    requirements = sa.Table("requirements", metadata, autoload_with=connection)
    rows = connection.execute(
        sa.select(services.c.service_id, services.c.project_id).where(
            services.c.provider == "mcp", services.c.template_id == "zentao"
        )
    ).all()
    project_services = {row.project_id: row.service_id for row in rows}
    service_projects = {row.service_id: row.project_id for row in rows}
    connections = dict(connection.execute(sa.select(auth.c.connection_id, auth.c.service_id)).all())
    sprint_projects = dict(
        connection.execute(sa.select(sprints.c.sprint_id, sprints.c.project_id)).all()
    )
    requirement_projects = dict(
        connection.execute(
            sa.select(requirements.c.requirement_id, sprints.c.project_id).join(
                sprints, requirements.c.sprint_id == sprints.c.sprint_id
            )
        ).all()
    )
    for row in connection.execute(sa.select(bindings).where(bindings.c.provider == "zentao")):
        pid = (
            row.local_resource_id
            if row.local_resource_type == "project"
            else (
                sprint_projects if row.local_resource_type == "sprint" else requirement_projects
            ).get(row.local_resource_id)
        )
        candidate = connections.get(row.connection_id)
        sid = candidate if service_projects.get(candidate) == pid else project_services.get(pid)
        if not sid:
            continue
        extra = row.extra_json or {}
        if isinstance(extra, str):
            extra = json.loads(extra)
        extra = {**extra, "mcpServiceId": sid}
        connection.execute(
            bindings.update()
            .where(bindings.c.binding_id == row.binding_id)
            .values(
                extra_json=extra
                if isinstance(bindings.c.extra_json.type, sa.JSON)
                else json.dumps(extra)
            )
        )
    with op.batch_alter_table("shared_services") as batch:
        batch.drop_constraint("uk_shared_service_template", type_="unique")


def downgrade():
    connection = op.get_bind()
    services = sa.table(
        "shared_services", sa.column("project_id"), sa.column("provider"), sa.column("template_id")
    )
    duplicates = connection.execute(
        sa.select(services.c.project_id)
        .where(services.c.template_id.is_not(None))
        .group_by(services.c.project_id, services.c.provider, services.c.template_id)
        .having(sa.func.count() > 1)
    ).first()
    if duplicates:
        raise RuntimeError("Cannot downgrade while a project has multiple services of one MCP type")
    with op.batch_alter_table("shared_services") as batch:
        batch.create_unique_constraint(
            "uk_shared_service_template", ["project_id", "provider", "template_id"]
        )
