"""Execution persistence adapter for orchestration-only tests with in-memory business rows.

Real transaction/attempt tests use SqlExecutionWriter and a database, never this adapter.
"""

from dataclasses import dataclass, field
from typing import Any

from support.execution_intent import ExecutionIntent


@dataclass
class MemoryExecutionWriter:
    writes: list[tuple[Any, ExecutionIntent, Any]] = field(default_factory=list)

    async def save(self, session, run, *, intent=ExecutionIntent(), worker=None):
        self.writes.append((run, intent, worker))
