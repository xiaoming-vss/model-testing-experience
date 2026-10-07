from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")]
TaskType = Literal["zentao_bug_sync", "zentao_bug_fields_update"]
StepKind = Literal["create_bug", "upload_attachment", "update_description", "update_fields"]


class IntegrationProtocolModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class IntegrationSummaryResult(IntegrationProtocolModel):
    steps: dict[str, str] = Field(default_factory=dict)


class IntegrationJobSummary(IntegrationProtocolModel):
    job_id: str
    job_status: str
    task_type: str
    protocol_version: int
    result: IntegrationSummaryResult = Field(default_factory=IntegrationSummaryResult)
    queue_reason: (
        Literal[
            "waiting",
            "paused",
            "worker_offline",
            "worker_incompatible",
            "target_busy",
            "runtime_changed",
        ]
        | None
    ) = None
    queue_wait_seconds: int | None = Field(default=None, ge=0)


class IntegrationStepPlan(IntegrationProtocolModel):
    step_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    kind: StepKind
    dependencies: list[str] = Field(default_factory=list)
    input: dict[str, Any] = Field(default_factory=dict)


class IntegrationSubmission(IntegrationProtocolModel):
    request_id: Identifier
    task_type: TaskType
    project_id: Identifier
    bug_id: Identifier
    actor_user_id: Identifier
    service_id: Identifier
    connection_id: Identifier
    target_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot: dict[str, Any]
    mapping: dict[str, Any] = Field(default_factory=dict)
    steps: list[IntegrationStepPlan] = Field(min_length=1, max_length=500)


class IntegrationClaimRequest(IntegrationProtocolModel):
    worker_id: str = Field(min_length=1, max_length=128)
    claim_request_id: Identifier
    protocol_versions: list[Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]] = Field(
        min_length=1, max_length=10
    )
    # Future Workers may advertise extra types; dispatch only the stored/capability intersection.
    task_types: list[
        Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")]
    ] = Field(min_length=1, max_length=10)


class IntegrationWorkerIdentity(IntegrationProtocolModel):
    worker_id: str = Field(min_length=1, max_length=128)
    claim_generation: int = Field(gt=0)
    runtime_generation: Identifier


class IntegrationPrepareRequest(IntegrationWorkerIdentity):
    prepare_request_id: Identifier
    input_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    access_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    input: dict[str, Any] = Field(json_schema_extra={"additionalProperties": {}})
    decision: Literal["write", "noop", "failed"] = "write"


class IntegrationRemoteResult(IntegrationProtocolModel):
    remote_bug_id: int | None = Field(default=None, gt=0, le=2_147_483_647)
    remote_file_id: int | None = Field(default=None, gt=0, le=2_147_483_647)
    description_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    opened_build: list[str] | None = Field(default=None, max_length=50)
    assigned_to: str | None = Field(default=None, max_length=100)
    error_code: (
        Literal[
            "remote_rejected",
            "remote_unavailable",
            "remote_uncertain",
            "baseline_changed",
            "input_changed",
            "access_revoked",
            "dependency_failed",
            "lease_lost",
            "canceled",
        ]
        | None
    ) = None


class IntegrationResultRequest(IntegrationWorkerIdentity):
    event_id: Identifier
    operation_id: Identifier
    status: Literal["succeeded", "failed", "unknown"]
    result: IntegrationRemoteResult = Field(default_factory=IntegrationRemoteResult)
    remote_duration_ms: int | None = Field(default=None, strict=True, ge=0, le=86_400_000)


class IntegrationFailureRequest(IntegrationWorkerIdentity):
    event_id: Identifier
    error_code: Literal[
        "remote_rejected",
        "remote_unavailable",
        "baseline_changed",
        "input_changed",
        "access_revoked",
        "dependency_failed",
        "canceled",
    ]
