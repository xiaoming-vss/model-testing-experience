"""Existing six-state records and their original audit trail survive conversion."""

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from test_initial_schema_migration import migration_config

from alembic import command


def seed(connection):
    config = migration_config(connection)
    command.upgrade(config, "20261004_0028")
    meta = sa.MetaData()
    meta.reflect(bind=connection)
    now = datetime.now(UTC)
    connection.execute(
        meta.tables["users"].insert(),
        {"user_id": "u", "nickname": "u", "password": "", "created_at": now, "updated_at": now},
    )
    connection.execute(
        meta.tables["projects"].insert(),
        {
            "project_id": "p",
            "user_id": "u",
            "name": "p",
            "description": "",
            "created_at": now,
            "updated_at": now,
        },
    )
    states = [
        "pending",
        "processing",
        "pending_regression",
        "closed",
        "reopened",
        "rejected",
        "rejected",
        "rejected",
    ]
    bugs = meta.tables["bugs"]
    for i, state in enumerate(states, 1):
        connection.execute(
            bugs.insert(),
            {
                "bug_id": f"b{i}",
                "bug_no": i,
                "project_id": "p",
                "title": f"bug{i}",
                "description_html": "<p>保留正文</p>",
                "status": state,
                "severity": "normal",
                "priority": "medium",
                "reporter_user_id": "u",
                "assignee_user_id": "u",
                "found_sprint_id": "s",
                "planned_fix_sprint_id": "",
                "requirement_id": "",
                "source_order_id": "",
                "source_entry_id": "",
                "source_case_id": "",
                "source_order_name": "",
                "source_case_title": "",
                "created_at": now,
                "updated_at": now,
            },
        )
    histories = meta.tables["bug_activities"]
    for i, reason in [(6, "by_design"), (7, "not_reproducible"), (8, "deferred")]:
        connection.execute(
            histories.insert(),
            {
                "activity_id": f"a{i}",
                "bug_id": f"b{i}",
                "kind": "status_change",
                "actor_user_id": "u",
                "action": "reject",
                "from_status": "pending",
                "to_status": "rejected",
                "content": "原始说明",
                "detail_json": {"rejectReason": reason},
                "created_at": now,
            },
        )
    for i, action in [
        (2, "confirm"),
        (3, "submit_fix"),
        (4, "regression_pass"),
        (5, "confirm"),
        (5, "regression_fail"),
    ]:
        connection.execute(
            histories.insert(),
            {
                "activity_id": f"a{i}-{action}",
                "bug_id": f"b{i}",
                "kind": "status_change",
                "actor_user_id": "u",
                "action": action,
                "from_status": "processing",
                "to_status": states[i - 1],
                "content": "历史处理",
                "detail_json": {},
                "created_at": now,
            },
        )
    connection.commit()
    return config, meta


def test_all_old_states_migrate_without_rewriting_history_or_bug_identity():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        config, meta = seed(connection)
        original_bugs = list(
            connection.execute(
                sa.select(meta.tables["bugs"]).order_by(meta.tables["bugs"].c.id)
            ).mappings()
        )
        histories = list(connection.execute(sa.select(meta.tables["bug_activities"])).mappings())
        command.upgrade(config, "head")
        bugs = sa.Table("bugs", sa.MetaData(), autoload_with=connection)
        rows = list(connection.execute(sa.select(bugs).order_by(bugs.c.id)).mappings())
        assert [(r["status"], bool(r["confirmed"]), r["resolution"]) for r in rows] == [
            ("active", False, ""),
            ("active", True, ""),
            ("resolved", True, "fixed"),
            ("closed", True, "fixed"),
            ("active", True, ""),
            ("resolved", False, "bydesign"),
            ("resolved", False, "notrepro"),
            ("resolved", False, "postponed"),
        ]
        assert all(r["resolved_build"] == "" for r in rows)
        assert rows[4]["activated_count"] == 1
        for before, after in zip(original_bugs, rows, strict=True):
            assert {k: after[k] for k in before if k != "status"} == {
                k: v for k, v in before.items() if k != "status"
            }
        assert (
            list(connection.execute(sa.select(meta.tables["bug_activities"])).mappings())
            == histories
        )
        command.downgrade(config, "20261004_0028")
        assert (
            list(
                connection.execute(
                    sa.select(meta.tables["bugs"]).order_by(meta.tables["bugs"].c.id)
                ).mappings()
            )
            == original_bugs
        )
        assert (
            list(connection.execute(sa.select(meta.tables["bug_activities"])).mappings())
            == histories
        )
        command.upgrade(config, "head")
        connection.execute(
            bugs.update().where(bugs.c.bug_id == "b6").values(resolution="willnotfix")
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="无法无损降级"):
            command.downgrade(config, "20261004_0028")
        connection.rollback()
        assert "resolution" in {c["name"] for c in sa.inspect(connection).get_columns("bugs")}
    engine.dispose()


@pytest.mark.parametrize("broken", ["state", "reason"])
def test_unknown_state_or_missing_reason_stops_before_schema_changes(broken):
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        config, meta = seed(connection)
        if broken == "state":
            connection.execute(
                meta.tables["bugs"]
                .update()
                .where(meta.tables["bugs"].c.bug_id == "b1")
                .values(status="unknown")
            )
        else:
            connection.execute(
                meta.tables["bug_activities"]
                .delete()
                .where(meta.tables["bug_activities"].c.bug_id == "b6")
            )
        connection.commit()
        with pytest.raises(RuntimeError, match="未知 Bug 状态|缺少有效拒绝原因"):
            command.upgrade(config, "head")
        connection.rollback()
        assert "confirmed" not in {c["name"] for c in sa.inspect(connection).get_columns("bugs")}
    engine.dispose()
