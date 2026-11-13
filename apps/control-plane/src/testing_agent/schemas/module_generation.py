"""Safe module-agent progress carried inside existing Worker summaries."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class ModuleAgentProgress(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", strict=True
    )

    id: str = Field(min_length=1, max_length=128)
    module: str = Field(min_length=1, max_length=512)
    status: Literal["queued", "running", "repairing", "completed", "failed", "canceled"]
    elapsed_ms: int = Field(ge=0)
    case_count: int = Field(ge=0)
    point_count: int = Field(default=0, ge=0)
    repair_attempt: int = Field(ge=0, le=2)


class ModuleGenerationProgress(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", strict=True
    )

    stage: Literal["detailed_cases", "case_names"] = "detailed_cases"
    review_round: int = Field(default=0, ge=0, le=4)
    issue_count: int = Field(default=0, ge=0)
    sequence: int = Field(ge=1)
    concurrency: int = Field(ge=1, le=32)
    status: Literal[
        "running",
        "merging",
        "reviewing",
        "revising",
        "review_failed",
        "completed",
        "failed",
        "canceled",
    ]
    modules: list[ModuleAgentProgress] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def consistent_modules(self) -> "ModuleGenerationProgress":
        if len({module.id for module in self.modules}) != len(self.modules):
            raise ValueError("module IDs must be unique")
        active = sum(module.status in {"running", "repairing"} for module in self.modules)
        if active > self.concurrency:
            raise ValueError("active modules exceed concurrency")
        if self.status in {"reviewing", "revising", "review_failed"} and self.stage != "case_names":
            raise ValueError("review progress is only valid for test points")
        if self.status in {"reviewing", "revising", "review_failed", "completed"} and any(
            module.status != "completed" for module in self.modules
        ):
            raise ValueError("completed generation must contain only completed modules")
        return self


class ModuleGenerationView(ModuleGenerationProgress):
    attempt_id: str
