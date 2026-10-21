"""Real HTTP page, identity, summary and permission contracts."""

import json

import sqlalchemy as sa
from support.function_case_library import make_case, make_requirement, make_sprint, make_suite
from support.order_api import make_order
from support.project_api import account, project
from support.project_api import api as api


def test_pages_focus_resume_lookup_and_detail_are_scoped(api):
    _, owner = account(api, "page-owner")
    _, outsider = account(api, "page-outsider")
    project_id = project(api, owner)
    sprint = make_sprint(api, owner, project_id)
    requirement = make_requirement(api, owner, sprint)
    suite = make_suite(api, owner, requirement)
    content = {"preconditions": ["large " * 1000], "steps": [{"action": "a", "expected": "b"}]}
    cases = [
        make_case(api, owner, suite, title=f"case {index}", content=content) for index in range(25)
    ]
    order_id = make_order(api, owner, sprint)["orderId"]
    base = f"/v1/test-orders/{order_id}/entries"
    assert (
        api.post(
            f"/v1/test-orders/{order_id}/cases", headers=owner, json={"caseIds": cases}
        ).status_code
        == 200
    )
    first = api.get(base, headers=owner).json()["data"]
    second = api.get(base, headers=owner, params={"page": 2}).json()["data"]
    assert first["total"] == second["total"] == 25
    assert len(first["items"]) == 20 and len(second["items"]) == 5
    assert all("snapshot" not in row and row["stepCount"] == 1 for row in first["items"])
    assert len(json.dumps(first)) < 20000
    last = second["items"][-1]["entryId"]
    focused = api.get(base, headers=owner, params={"focusEntryId": last}).json()["data"]
    assert focused["page"] == 2 and focused["preferredEntryId"] == last
    marked = api.post(
        base + "/batch-mark-passed",
        headers=owner,
        json={"entryIds": [row["entryId"] for row in first["items"]]},
    )
    assert marked.status_code == 200
    resumed = api.get(base, headers=owner, params={"resume": "true"}).json()["data"]
    assert resumed["page"] == 2 and resumed["preferredEntryId"] == second["items"][0]["entryId"]
    assert (
        api.get(base, headers=owner, params={"resume": "true", "afterEntryId": last}).json()[
            "data"
        ]["preferredEntryId"]
        == ""
    )
    detail = api.get(base + "/" + last, headers=owner).json()["data"]
    assert detail["snapshot"] == content and detail["caseTitle"] == "case 24"
    lookup = api.post(base + "/lookup", headers=owner, json={"caseIds": [cases[-1], "absent"]})
    assert lookup.status_code == 200 and lookup.json()["data"]["total"] == 1
    assert "snapshot" not in lookup.json()["data"]["items"][0]
    other = make_order(api, owner, sprint, name="other")["orderId"]
    assert api.get(f"/v1/test-orders/{other}/entries/{last}", headers=owner).status_code == 404
    assert api.get(base + "/" + last, headers=outsider).status_code == 403
    assert (
        api.post(base + "/lookup", headers=outsider, json={"caseIds": cases[:1]}).status_code == 403
    )
    retest = api.post(
        f"/v1/sprints/{sprint}/test-orders",
        headers=owner,
        json={"name": "retest", "sourceOrderId": order_id},
    ).json()["data"]
    retest_entries = api.get(f"/v1/test-orders/{retest['orderId']}/entries", headers=owner).json()[
        "data"
    ]
    assert retest_entries["total"] == 5
    assert all(item["stepCount"] == 1 for item in retest_entries["items"])
    for params in ({"page": 0}, {"pageSize": 101}, {"status": "unknown"}):
        assert api.get(base, headers=owner, params=params).status_code == 400
    assert (
        api.post(base + "/lookup", headers=owner, json={"caseIds": ["x"] * 501}).status_code == 400
    )


def test_migration_backfills_frozen_step_count():
    from support.initial_schema_migration import migration_config
    from support.mysql_initialization import seed_row

    from alembic import command

    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        config = migration_config(connection)
        command.upgrade(config, "20261021_0047")
        legacy = sa.Table("test_order_entries", sa.MetaData(), autoload_with=connection)
        row = seed_row(
            connection,
            legacy,
            {
                "snapshot_json": {
                    "steps": [{"action": "a", "expected": "b"}, {"action": "c", "expected": "d"}]
                }
            },
        )
        connection.commit()
        command.upgrade(config, "head")
        assert (
            connection.scalar(
                sa.text("SELECT step_count FROM test_order_entries WHERE id=:id"), {"id": row["id"]}
            )
            == 2
        )
        command.downgrade(config, "20261021_0047")
        assert "step_count" not in {
            column["name"] for column in sa.inspect(connection).get_columns("test_order_entries")
        }
    engine.dispose()
