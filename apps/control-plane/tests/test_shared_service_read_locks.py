import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql

from testing_agent.services.shared_service import SharedServiceService


@pytest.mark.parametrize(
    "action, lock, expected",
    [("read", False, False), ("read", True, True), ("manage", False, True)],
)
def test_shared_service_only_locks_mutations(action, lock, expected):
    statements = []

    class Session:
        async def scalar(self, statement):
            statements.append(str(statement.compile(dialect=mysql.dialect())))
            return SimpleNamespace(project_id="fixture", user_id="owner")

    service = SharedServiceService(SimpleNamespace(repository=SimpleNamespace(session=Session())))
    asyncio.run(
        service.get_resource("owner", "fixture", "llm", "service", action=action, lock=lock)
    )
    assert len(statements) == 2
    assert all(("FOR UPDATE" in statement) == expected for statement in statements)
