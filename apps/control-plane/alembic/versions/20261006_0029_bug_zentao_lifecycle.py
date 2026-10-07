"""Align native Bug state with ZenTao without rewriting its audit history."""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0029"
down_revision = "20261004_0028"
branch_labels = None
depends_on = None


def tables():
    meta = sa.MetaData()
    bind = op.get_bind()
    return (
        sa.Table("bugs", meta, autoload_with=bind),
        sa.Table("bug_activities", meta, autoload_with=bind),
    )


def upgrade():
    bind = op.get_bind()
    bugs, activities = tables()
    # Validate before DDL (MySQL DDL commits implicitly).
    old_states = {"pending", "processing", "pending_regression", "closed", "rejected", "reopened"}
    if set(bind.scalars(sa.select(bugs.c.status).distinct())) - old_states:
        raise RuntimeError("存在未知 Bug 状态，请先核对后迁移")
    histories = {}
    for row in bind.execute(sa.select(activities).order_by(activities.c.id)).mappings():
        if row["kind"] == "status_change":
            histories.setdefault(row["bug_id"], []).append(row)
    reasons = {"by_design": "bydesign", "not_reproducible": "notrepro", "deferred": "postponed"}
    rows = list(bind.execute(sa.select(bugs)).mappings())
    for row in rows:
        if row["status"] == "rejected":
            rejects = [
                h for h in histories.get(row["bug_id"], []) if h["action"] in {"reject", "resolve"}
            ]
            detail = (rejects[-1]["detail_json"] or {}) if rejects else {}
            if not rejects or not (
                detail.get("rejectReason") in reasons
                or detail.get("toResolution") in reasons.values()
            ):
                raise RuntimeError("已拒绝 Bug 缺少有效拒绝原因，不能猜测解决方案")
    for column in (
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("resolution", sa.String(20), nullable=False, server_default=""),
        sa.Column("resolved_build", sa.String(255), nullable=False, server_default=""),
        sa.Column("duplicate_bug", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activated_count", sa.Integer(), nullable=False, server_default="0"),
    ):
        op.add_column("bugs", column)
    bugs, _ = tables()
    mapping = {
        "pending": "active",
        "processing": "active",
        "reopened": "active",
        "pending_regression": "resolved",
        "rejected": "resolved",
        "closed": "closed",
    }
    for row in rows:
        history = histories.get(row["bug_id"], [])
        resolution = "fixed" if row["status"] in {"pending_regression", "closed"} else ""
        if row["status"] == "rejected":
            reject = [h for h in history if h["action"] in {"reject", "resolve"}][-1]
            detail = reject["detail_json"] or {}
            resolution = detail.get("toResolution") or reasons[detail["rejectReason"]]
        activated = sum(h["action"] in {"reopen", "regression_fail", "activate"} for h in history)
        confirmed = row["status"] in {"processing", "pending_regression", "closed"} or any(
            h["action"] in {"confirm", "submit_fix"} for h in history
        )
        if history and (history[-1]["detail_json"] or {}).get("toConfirmed") is not None:
            confirmed = bool(history[-1]["detail_json"]["toConfirmed"])
        resolutions = [h for h in history if h["action"] in {"resolve", "submit_fix"}]
        build = (
            (resolutions[-1]["detail_json"] or {}).get("resolvedBuild", "") if resolutions else ""
        )
        bind.execute(
            bugs.update()
            .where(bugs.c.id == row["id"])
            .values(
                resolved_build=build if resolution == "fixed" else "",
                status=mapping[row["status"]],
                confirmed=confirmed,
                resolution=resolution,
                activated_count=max(activated, int(row["status"] == "reopened")),
            )
        )
    # No historical build was recorded; leave resolved_build empty rather than inventing one.


def downgrade():
    bind = op.get_bind()
    bugs, activities = tables()
    latest = {}
    for row in bind.execute(sa.select(activities).order_by(activities.c.id)).mappings():
        if row["kind"] == "status_change":
            latest[row["bug_id"]] = row
    rows = list(bind.execute(sa.select(bugs)).mappings())
    # New resolution categories cannot be represented by the old three reject reasons.
    if any(r["resolution"] not in {"", "fixed", "bydesign", "notrepro", "postponed"} for r in rows):
        raise RuntimeError("新解决方案无法无损降级，请先备份并处理 Bug 数据")
    if any(r["status"] == "closed" and r["resolution"] not in {"", "fixed"} for r in rows):
        raise RuntimeError("非修复关闭无法无损降级，请先备份并处理 Bug 数据")
    for row in rows:
        event = latest.get(row["bug_id"], {})
        if row["status"] == "closed":
            status = "closed"
        elif row["status"] == "resolved":
            status = "pending_regression" if row["resolution"] == "fixed" else "rejected"
        elif event.get("action") in {"activate", "reopen", "regression_fail"} or (
            not event and row["activated_count"]
        ):
            status = "reopened"
        else:
            status = "processing" if row["confirmed"] else "pending"
        bind.execute(bugs.update().where(bugs.c.id == row["id"]).values(status=status))
    for name in ("activated_count", "duplicate_bug", "resolved_build", "resolution", "confirmed"):
        op.drop_column("bugs", name)
