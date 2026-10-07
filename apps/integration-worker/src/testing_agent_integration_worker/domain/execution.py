import time
from collections.abc import Callable
from dataclasses import dataclass, field

from testing_agent_integration_worker.schemas.job import ClaimJob


@dataclass
class ExecutionWindow:
    deadline: float
    margin: float = 2
    stopped: bool = False
    lost: bool = False
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    def active(self) -> bool:
        return not self.stopped and self.alive()

    def alive(self) -> bool:
        return not self.lost and self.clock() < self.deadline

    def renew(self, started: float, seconds: float) -> bool:
        if not self.alive():
            self.stopped = True
            self.lost = True
            return False
        self.deadline = started + seconds - self.margin
        if not self.alive():
            self.stopped = True
            self.lost = True
            return False
        return True


@dataclass
class Execution:
    claim: ClaimJob
    window: ExecutionWindow
