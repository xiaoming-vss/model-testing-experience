"""Retry only known-aborted local MySQL transactions, never remote execution."""

import asyncio
from functools import wraps

from sqlalchemy.exc import OperationalError


def local_transaction(command):
    @wraps(command)
    async def run(self, *args, **kwargs):
        for attempt in range(3):
            try:
                return await command(self, *args, **kwargs)
            except OperationalError as error:
                code = getattr(error.orig, "args", (None,))[0]
                await self.session.rollback()
                if code not in {1205, 1213} or attempt == 2:
                    raise
                await asyncio.sleep(0.025 * (attempt + 1))

    return run
