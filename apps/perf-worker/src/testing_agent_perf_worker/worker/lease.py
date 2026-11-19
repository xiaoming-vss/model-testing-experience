"""Monotonic execution lease tracking."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class ExecutionWindow:
    lease_seconds: int
    margin_seconds: int
    deadline: float
    lost: bool = False
    stopped: bool = False

    @classmethod
    def start(
        cls,
        lease_seconds: int,
        margin_seconds: int,
        *,
        started_monotonic: float | None = None,
    ) -> ExecutionWindow:
        started = time.monotonic() if started_monotonic is None else started_monotonic
        return cls(
            lease_seconds=lease_seconds,
            margin_seconds=margin_seconds,
            deadline=started + max(lease_seconds - margin_seconds, 1),
        )

    def active(self, *, now: float | None = None) -> bool:
        return not self.lost and not self.stopped and self.alive(now=now)

    def alive(self, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        return not self.lost and current < self.deadline

    def remaining_seconds(self, *, now: float | None = None) -> float:
        current = time.monotonic() if now is None else now
        return max(0.0, self.deadline - current)

    def renew(
        self,
        lease_seconds: int,
        *,
        started_monotonic: float,
        now: float | None = None,
    ) -> bool:
        if self.lost:
            return False
        current = time.monotonic() if now is None else now
        next_deadline = started_monotonic + max(lease_seconds - self.margin_seconds, 1)
        if next_deadline <= current:
            self.lose()
            return False
        self.lease_seconds = lease_seconds
        self.deadline = next_deadline
        return True

    def stop(self) -> None:
        self.stopped = True

    def lose(self) -> None:
        self.lost = True
        self.stopped = True
