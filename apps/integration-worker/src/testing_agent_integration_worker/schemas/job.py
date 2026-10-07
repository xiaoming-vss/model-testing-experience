from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic.alias_generators import to_camel

TaskType = Literal["zentao_bug_sync", "zentao_bug_fields_update"]
StepKind = Literal["create_bug", "upload_attachment", "update_description", "update_fields"]


class WireModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Identity(WireModel):
    worker_id: str = Field(min_length=1, max_length=128)
    claim_generation: int = Field(gt=0)
    runtime_generation: str = Field(min_length=1, max_length=64)


class ClaimJob(Identity):
    job_id: str
    job_status: str
    task_type: TaskType
    protocol_version: Literal[1]
    result: dict[str, Any] = Field(default_factory=dict, repr=False)
    lease_seconds: float = Field(gt=0)

    def identity(self) -> Identity:
        return Identity(
            worker_id=self.worker_id,
            claim_generation=self.claim_generation,
            runtime_generation=self.runtime_generation,
        )


class ClaimResponse(WireModel):
    job: ClaimJob | None


class JobStep(WireModel):
    step_key: str
    kind: StepKind
    status: str
    dependencies: list[str]
    input: dict[str, Any] = Field(repr=False)


class JobInput(WireModel):
    job_id: str
    job_status: str
    task_type: TaskType
    protocol_version: Literal[1]
    result: dict[str, Any] = Field(repr=False)
    snapshot: dict[str, Any] = Field(repr=False)
    mapping: dict[str, Any] = Field(repr=False)
    input_revision: str
    target_revision: str
    steps: list[JobStep]


class Access(WireModel):
    endpoint: str
    token: SecretStr
    access_revision: str = ""
