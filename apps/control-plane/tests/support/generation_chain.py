"""Shared generation-chain DB helpers; no collected tests."""

from sqlalchemy import select

from testing_agent.models.worker_task import WorkerTask


def latest_worker(session, run_id="run"):
    return session.scalars(
        select(WorkerTask)
        .where(WorkerTask.run_id == run_id)
        .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
    ).first()
