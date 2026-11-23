"""Public candidate workflow is authorized and blocks legacy writes after binding."""

import asyncio
from uuid import uuid4

from sqlalchemy import text
from support.project_api import account, api, project, requirement  # noqa: F401


def test_initialize_read_and_legacy_cutover_guard(api):  # noqa: F811
    _, owner = account(api, "workflow-owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    _, viewer = account(api, "workflow-viewer")
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "workflow-viewer", "role": "viewer"},
        ).status_code
        == 200
    )
    config = api.post(
        f"/v1/requirements/{rid}/design/function/configuration", headers=owner, json={}
    )
    assert config.status_code == 200, config.text
    task_id = config.json()["data"]["taskId"]
    base = f"/v1/requirements/{rid}/generation/function"
    assert (
        api.post(base + "/candidate-chain", headers=viewer, json={"taskId": task_id}).status_code
        == 403
    )
    first = api.post(base + "/candidate-chain", headers=owner, json={"taskId": task_id})
    assert first.status_code == 200, first.text
    assert not first.json()["data"]["created"]
    again = api.post(base + "/candidate-chain", headers=owner, json={"taskId": task_id})
    assert again.status_code == 200 and not again.json()["data"]["created"]
    stage = base + "/stages/case_names"
    current = api.get(stage + "/current", headers=viewer)
    assert current.status_code == 200, current.text
    state = current.json()["data"]
    assert state["candidateId"] is None and state["currentToken"] and not state["active"]
    assert state["sourceTrace"] == []
    legacy = api.post(stage + "/run", headers=owner, json={"connectionId": "missing"})
    assert legacy.status_code == 404
    second_config = api.post(
        f"/v1/requirements/{rid}/design/function/configuration",
        headers=owner,
        json={"newConfiguration": True},
    )
    assert second_config.status_code == 400 and "当前生成链" in second_config.text
    unavailable = api.post(
        stage + "/candidate-run",
        headers=owner,
        json={"connectionId": "missing", "requestId": str(uuid4())},
    )
    assert unavailable.status_code == 404


def test_legacy_database_without_candidate_tables_requires_upgrade(api):  # noqa: F811
    _, owner = account(api, "legacy-schema-owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)

    async def remove_candidate_tables():
        async with api.app.state.test_sessions() as session:
            for name in (
                "ai_generation_review_receipts",
                "ai_generation_stage_contents",
                "ai_generation_candidates",
                "requirement_generation_chains",
            ):
                await session.execute(text(f"DROP TABLE {name}"))
            await session.commit()

    asyncio.run(remove_candidate_tables())
    config = api.post(
        f"/v1/requirements/{rid}/design/function/configuration", headers=owner, json={}
    )
    assert config.status_code == 400 and "升级" in config.text
    overview = api.get(f"/v1/requirements/{rid}/generation", headers=owner)
    assert overview.status_code == 200, overview.text
    function = next(row for row in overview.json()["data"]["chains"] if row["kind"] == "function")
    assert not function["configured"]
    chain = api.get(f"/v1/requirements/{rid}/generation/function", headers=owner)
    assert chain.status_code == 200, chain.text
    init = api.post(
        f"/v1/requirements/{rid}/generation/function/candidate-chain",
        headers=owner,
        json={"taskId": "missing"},
    )
    assert init.status_code == 400 and "数据库升级" in init.text
    current = api.get(
        f"/v1/requirements/{rid}/generation/function/stages/case_names/current", headers=owner
    )
    assert current.status_code == 400 and "数据库升级" in current.text


def test_incomplete_candidate_schema_never_silently_falls_back_to_legacy(api):  # noqa: F811
    _, owner = account(api, "incomplete-schema-owner")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)

    async def remove_one_candidate_table():
        async with api.app.state.test_sessions() as session:
            await session.execute(text("DROP TABLE ai_generation_stage_contents"))
            await session.commit()

    asyncio.run(remove_one_candidate_table())
    response = api.get(f"/v1/requirements/{rid}/generation", headers=owner)
    assert response.status_code == 400 and "数据表不完整" in response.text
