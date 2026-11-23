"""Direct-stage transaction and worker/view regression tests."""

from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.models.ai_generation_stage import AiGenerationStage


async def test_unconfigured_chain_view_does_not_create_stages(db):  # noqa: F811
    from testing_agent.services.stage_storage.chain_view import build_chain_view

    seed_task(db)
    before = len(db.scalars(select(AiGenerationStage)).all())
    view = await build_chain_view(AsyncSessionAdapter(db), "r", "api", None, detail=True)
    assert [stage.stage for stage in view.stages] == [
        "interface_extract",
        "api_design",
        "generate",
    ]
    assert not view.configured
    assert len(db.scalars(select(AiGenerationStage)).all()) == before
