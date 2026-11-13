"""Module workspace isolation and compact, ordered progress snapshots."""

import asyncio
import inspect
import shutil
import time
from pathlib import Path
from typing import Any

from .validation import ValidationContext


def prepare_module_workspace(workspace: str | None, dispatch: str, index: int) -> str | None:
    """Copy skills so module agents cannot overwrite each other's working files."""
    if workspace is None:
        return None
    root = Path(workspace).resolve()
    target = root / "module-runs" / dispatch / str(index)
    target.mkdir(parents=True, exist_ok=True)
    if (root / "skills").is_dir():
        shutil.copytree(root / "skills", target / "skills", dirs_exist_ok=True)
    return str(target)


class ModuleProgress:
    """Serialize complete snapshots; never send prompts, credentials or partial cases."""

    def __init__(
        self,
        modules: list[str],
        execution: ValidationContext | None,
        *,
        stage: str = "detailed_cases",
    ) -> None:
        self.execution = execution
        self.stage = stage
        self.details: dict[str, Any] = {}
        self.sequence = 0
        self.status = "running"
        self.started: dict[int, float] = {}
        self.lock = asyncio.Lock()
        self.modules: list[dict[str, Any]] = [
            {
                "id": str(i),
                "module": name[:512],
                "status": "queued",
                "elapsedMs": 0,
                "caseCount": 0,
                "repairAttempt": 0,
                **({"pointCount": 0} if stage == "case_names" else {}),
            }
            for i, name in enumerate(modules)
        ]

    async def emit(
        self, index: int | None = None, status: str | None = None, **fields: Any
    ) -> None:
        async with self.lock:
            if index is not None:
                if status == "running":
                    self.started.setdefault(index, time.monotonic())
                self.modules[index].update(fields)
                if status:
                    self.modules[index]["status"] = status
                if index in self.started:
                    self.modules[index]["elapsedMs"] = round(
                        (time.monotonic() - self.started[index]) * 1000
                    )
            else:
                if status:
                    self.status = status
                self.details.update(fields)
            self.sequence += 1
            snapshot = {
                "sequence": self.sequence,
                "stage": self.stage,
                **self.details,
                "concurrency": 2,
                "status": self.status,
                "modules": [dict(module) for module in self.modules],
            }
            if self.execution:
                reported = await asyncio.to_thread(
                    self.execution.report, {"stage": self.stage, "moduleGeneration": snapshot}
                )
                if inspect.isawaitable(reported):
                    await reported

    async def stop(self, status: str) -> None:
        for index, module in enumerate(self.modules):
            if module["status"] in {"queued", "running", "repairing"}:
                module["status"] = "canceled"
                if index in self.started:
                    module["elapsedMs"] = round((time.monotonic() - self.started[index]) * 1000)
        await self.emit(status=status)
