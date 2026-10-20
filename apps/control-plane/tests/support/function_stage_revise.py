"""Shared preparation for function stage revise tests; no collected cases."""

import asyncio
from types import SimpleNamespace

from authorization_database import AuthorizationDatabase

from support.function_candidate_review import FunctionReviewRepository, make_run


class RevisionRepository(FunctionReviewRepository):
    session = AuthorizationDatabase()

    def __init__(self, run):
        super().__init__(run)
        self.queued = []
        self.lock = asyncio.Lock()
        self.latest = SimpleNamespace(llm_connection_id="llm-1")

    async def get_run_for_update(self, run_id):
        await self.lock.acquire()
        return self.run

    async def get_latest_ai_dispatch(self, run_id):
        return self.latest

    def add(self, task):
        self.queued.append(task)

    async def commit(self):
        await super().commit()
        if self.lock.locked():
            self.lock.release()

    async def get_project(self, project_id):
        return SimpleNamespace(user_id="user-1", project_id="project-1")


def revision_run(stage="requirement_analysis"):
    run = make_run(status="waiting_review")
    run.checkpoint_enabled = True
    run.current_stage = stage
    run.stage_status = "waiting_review"
    run.config_json = {"requirementAnalysis": {"old": True}, "caseNames": {"categories": []}}
    if stage == "detailed_cases":
        run.status = "success"
        run.result_yaml = '{"cases":[{"name":"existing", "module":"login"}]}'
    return run
