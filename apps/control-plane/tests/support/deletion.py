"""Explicit deletion adapter for orchestration tests using in-memory repositories.

Database, locking, lifecycle and rollback tests use SqlResourceDeletion.
"""


class MemoryResourceDeletion:
    def __init__(self, repository):
        self.repository = repository

    async def delete(self, session, resource):
        await self.repository.hard_delete(resource)
