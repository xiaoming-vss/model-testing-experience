"""Immutable execution identities, separate from mutable queue/lease state."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AiWorkerContext:
    generate_task_id: str | None
    llm_connection_id: str | None
    domain: Literal["ai"] = "ai"


@dataclass(frozen=True)
class AiDispatchContext:
    """Latest dispatch facts used when deciding whether/how to launch a follow-up."""

    task_id: str
    status: str
    llm_connection_id: str | None


@dataclass(frozen=True)
class ApiWorkerContext:
    case_id: str | None
    collection_id: str | None
    collection_run_id: str | None
    domain: Literal["api"] = "api"


@dataclass(frozen=True)
class UiWorkerContext:
    case_id: str | None
    suite_id: str | None
    domain: Literal["ui"] = "ui"


type WorkerExecutionContext = AiWorkerContext | ApiWorkerContext | UiWorkerContext
