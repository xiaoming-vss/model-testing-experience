"""List HTTP contracts: bounded payloads, batch binding reads and project isolation."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from support.project_api import account, api, project  # noqa: F401

from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint

NOW = datetime(2026, 10, 4, tzinfo=UTC)


@pytest.fixture
def lists(api):  # noqa: F811
    user, owner = account(api, "owner")
    _, outsider = account(api, "outsider")
    pid = project(api, owner)
    other = project(api, owner, "other")

    async def seed():
        async with api.app.state.test_sessions() as session:
            session.add_all(
                [
                    Sprint(
                        sprint_id=sid,
                        project_id=p,
                        name=sid,
                        start_time=NOW,
                        end_time=NOW + timedelta(days=1),
                        created_at=NOW,
                    )
                    for sid, p in [("s1", pid), ("s2", pid), ("foreign", other)]
                ]
            )
            await session.flush()
            session.add_all(
                [
                    Requirement(
                        requirement_id=f"r{i}",
                        sprint_id="s1",
                        name=f"需求{i}",
                        document_content="large body " * 10_000,
                        created_at=NOW,
                    )
                    for i in range(25)
                ]
            )
            session.add(
                Requirement(requirement_id="foreign-r", sprint_id="foreign", name="其他项目")
            )
            await session.flush()
            for bid, kind, local, provider, status, remote in [
                ("sprint-binding", "sprint", "s1", "zentao", "active", "201"),
                ("req-binding", "requirement", "r24", "zentao", "active", "301"),
                ("disabled", "requirement", "r23", "zentao", "disabled", "302"),
                ("gitlab", "requirement", "r22", "gitlab", "active", "303"),
                ("gitlab2", "requirement", "r22", "gitlab", "active", "305"),
                ("gitlab-off", "requirement", "r23", "gitlab", "unbound", "306"),
                ("gitlab-foreign", "requirement", "foreign-r", "gitlab", "active", "307"),
                ("foreign-binding", "requirement", "foreign-r", "zentao", "active", "304"),
            ]:
                session.add(
                    ResourceBinding(
                        binding_id=bid,
                        user_id=user["userId"],
                        provider=provider,
                        connection_id="old-connection",
                        local_resource_type=kind,
                        local_resource_id=local,
                        remote_resource_type=(
                            "repository"
                            if provider == "gitlab"
                            else "execution"
                            if kind == "sprint"
                            else "story"
                        ),
                        extra_json={"branch": "dev", "private": "must-not-leak"},
                        remote_resource_id=remote,
                        remote_name_snapshot=bid,
                        status=status,
                    )
                )
            await session.commit()

    asyncio.run(seed())
    sql = []
    engine = api.app.state.test_sessions.kw["bind"].sync_engine

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        sql.append(statement)

    event.listen(engine, "before_cursor_execute", record)

    def read(path, *, as_outsider=False):
        return api.get(path, headers=outsider if as_outsider else owner)

    yield read, pid, sql
    event.remove(engine, "before_cursor_execute", record)


def test_requirement_pages_batch_bindings_and_do_not_load_document_bodies(lists):
    read, pid, sql = lists
    first = read(f"/v1/projects/{pid}/requirements?page=1&pageSize=20&sprintId=s1")
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["total"] == 25
    assert len(data["items"]) == 20
    assert [row["requirementId"] for row in data["items"]] == [f"r{i}" for i in range(24, 4, -1)]
    assert data["items"][0]["sprintName"] == "s1"
    assert data["items"][0]["zentaoBinding"] == {
        "bindingId": "req-binding",
        "provider": "zentao",
        "remoteResourceId": "301",
        "remoteNameSnapshot": "req-binding",
        "status": "active",
    }
    assert all(row["zentaoBinding"] is None for row in data["items"][1:])
    assert data["items"][2]["codeBindings"] == [
        {"repository": "gitlab", "branch": "dev"},
        {"repository": "gitlab2", "branch": "dev"},
    ]
    assert all(row["codeBindings"] == [] for row in data["items"] if row["requirementId"] != "r22")
    assert "must-not-leak" not in first.text
    assert data["items"][0]["createdAt"]
    assert all("documentContent" not in row for row in data["items"])
    assert len([s for s in sql if "FROM resource_bindings" in s]) == 2
    assert not any("requirements.document_content" in s for s in sql)
    second = read(f"/v1/projects/{pid}/requirements?page=2&pageSize=20").json()["data"]
    assert second["total"] == 25
    assert [row["requirementId"] for row in second["items"]] == [f"r{i}" for i in range(4, -1, -1)]
    assert read(f"/v1/projects/{pid}/requirements?sprintId=s2").json()["data"] == {
        "total": 0,
        "items": [],
    }
    # Existing detail consumers retain their document-content contract.
    detail = read("/v1/requirements/r24").json()["data"]
    assert detail["documentContent"].startswith("large body")


def test_sprint_list_includes_bindings_in_one_batch(lists):
    read, pid, sql = lists
    response = read(f"/v1/projects/{pid}/sprints")
    assert response.status_code == 200, response.text
    rows = {row["sprintId"]: row for row in response.json()["data"]["items"]}
    assert set(rows) == {"s1", "s2"}
    assert rows["s1"]["zentaoBinding"]["bindingId"] == "sprint-binding"
    assert rows["s2"]["zentaoBinding"] is None
    assert len([s for s in sql if "FROM resource_bindings" in s]) == 1


def test_project_requirement_lists_validate_scope_and_page_bounds(lists):
    read, pid, _ = lists
    assert read(f"/v1/projects/{pid}/requirements", as_outsider=True).status_code == 403
    assert read(f"/v1/projects/{pid}/requirements?sprintId=foreign").status_code == 404
    for params in ["page=0", "pageSize=0", "pageSize=101", "sprintId="]:
        assert read(f"/v1/projects/{pid}/requirements?{params}").status_code == 400
    beyond = read(f"/v1/projects/{pid}/requirements?page=3&pageSize=20").json()["data"]
    assert beyond == {"total": 25, "items": []}
