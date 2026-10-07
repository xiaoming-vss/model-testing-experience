"""Crash-safe minimal result outbox. Access material and task inputs have no schema slots."""

import json
import os
import tempfile
from pathlib import Path

from pydantic import Field

from testing_agent_integration_worker.schemas.job import WireModel
from testing_agent_integration_worker.schemas.step import ResultEvent


class Evidence(WireModel):
    job_id: str
    step_key: str
    event: ResultEvent = Field(repr=False)


class EvidenceRepository:
    def __init__(self, path: Path):
        self.path = path
        self.items: dict[str, Evidence] = {}
        if path.exists():
            values = json.loads(path.read_text())
            for value in values:
                evidence = Evidence.model_validate(value)
                self.items[evidence.event.event_id] = evidence

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(
                    [
                        item.model_dump(mode="json", by_alias=True, exclude_none=True)
                        for item in self.items.values()
                    ],
                    stream,
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def record(self, evidence: Evidence) -> None:
        self.items[evidence.event.event_id] = evidence
        self.save()

    def acknowledge(self, event_id: str) -> None:
        self.items.pop(event_id, None)
        self.save()
