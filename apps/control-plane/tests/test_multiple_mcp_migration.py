"""Keep legacy bindings pinned before removing the per-type catalog constraint."""

import json
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from support.initial_schema_migration import migration_config

from alembic import command


def test_backfill_preserves_original_service_and_downgrade_refuses_duplicates():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        config = migration_config(connection)
        command.upgrade(config, "20261004_0026")
        meta = sa.MetaData()
        meta.reflect(bind=connection)
        tables = meta.tables
        now = datetime.now(UTC)
        connection.execute(
            tables["users"].insert(),
            {"user_id": "u", "nickname": "u", "password": "", "created_at": now, "updated_at": now},
        )
        connection.execute(
            tables["projects"].insert(),
            {
                "project_id": "p",
                "user_id": "u",
                "name": "p",
                "description": "",
                "created_at": now,
                "updated_at": now,
            },
        )
        services = tables["shared_services"]
        connection.execute(
            services.insert(),
            {
                "service_id": "old",
                "project_id": "p",
                "name": "Old",
                "provider": "mcp",
                "template_id": "zentao",
                "base_url": "http://old.test/mcp",
                "model_id": "",
                "created_at": now,
                "updated_at": now,
            },
        )
        bindings = tables["resource_bindings"]
        connection.execute(
            bindings.insert(),
            {
                "binding_id": "b",
                "provider": "zentao",
                "user_id": "u",
                "connection_id": "deleted-legacy",
                "instance_url": "http://zentao.test",
                "instance_key": "old-instance",
                "local_resource_type": "project",
                "local_resource_id": "p",
                "remote_resource_type": "project",
                "remote_resource_id": "10",
                "remote_parent_id": "",
                "remote_name_snapshot": "",
                "status": "bound",
                "extra_json": {"preserved": 1},
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.commit()
        command.upgrade(config, "head")
        result = connection.scalar(sa.select(bindings.c.extra_json))
        if isinstance(result, str):
            result = json.loads(result)
        assert result == {"preserved": 1, "mcpServiceId": "old"}
        connection.execute(
            services.insert(),
            {
                "service_id": "second",
                "project_id": "p",
                "name": "Second",
                "provider": "mcp",
                "template_id": "zentao",
                "base_url": "http://new.test/mcp",
                "model_id": "",
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="multiple services"):
            command.downgrade(config, "20261004_0026")
        connection.rollback()
        assert connection.scalar(sa.select(sa.func.count()).select_from(services)) == 2
        connection.execute(services.delete().where(services.c.service_id == "second"))
        connection.commit()
        command.downgrade(config, "20261004_0026")
        assert "uk_shared_service_template" in {
            c["name"] for c in sa.inspect(connection).get_unique_constraints("shared_services")
        }
    engine.dispose()
