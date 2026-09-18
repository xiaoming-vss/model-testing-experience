from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


def parse_json_object(value: Any) -> dict[str, Any] | None:
    if value is None or isinstance(value, dict):
        return value
    if isinstance(value, str):
        if not value.strip():
            return {}
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Input should be a valid dictionary or JSON object string")


def accept_worker_json_text(value: Any) -> Any:
    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class WorkerClaimRequest(BaseModel):
    worker_id: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerTaskData(BaseModel):
    task_id: str = Field()
    task_type: str = Field()
    run_id: str = Field()
    status: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerClaimResponse(BaseModel):
    task: dict[str, Any] | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerClaimPayload(BaseModel):
    task_id: str = Field()
    task_type: str = Field()
    run_id: str = Field()
    domain: str | None = None
    suite_id: str | None = Field(default=None)
    case_id: str | None = Field(default=None)
    collection_run_id: str | None = Field(default=None)
    collection_id: str | None = Field(default=None)
    generate_task_id: str | None = Field(default=None)
    project_id: str | None = Field(default=None)
    sprint_id: str | None = Field(default=None)
    requirement_id: str | None = Field(default=None)
    llm_connection_id: str | None = Field(default=None)
    status: str | None = None
    checkpoint_enabled: bool | None = Field(default=None)
    current_stage: str | None = Field(default=None)
    config_json: str | None = Field(default=None)
    lease_seconds: int | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerSnapshotResponse(BaseModel):
    task_type: str | None = Field(default=None)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class WorkerTaskAckResponse(BaseModel):
    task_id: str = Field()
    worker_id: str | None = Field(default=None)
    status: str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerItemAckResponse(WorkerTaskAckResponse):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    item_id: str = Field()


class WorkerProjectSkillResponse(BaseModel):
    skill_space_id: str = Field()
    project_id: str = Field()
    version: int
    hash: str
    download_url: str = Field()
    filename: str
    size: int
    is_default: bool = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerProjectSkillsResponse(BaseModel):
    project_id: str = Field()
    skills: list[WorkerProjectSkillResponse]

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerLlmCredentialsResponse(BaseModel):
    task_id: str = Field()
    connection_id: str | None = Field(default=None)
    base_url: str = Field()
    model_id: str = Field()
    api_key: str = Field()
    organization: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerGitlabCredentialItem(BaseModel):
    connection_id: str = Field()
    base_url: str = Field()
    access_token: str = Field()
    repository_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerGitlabCredentialsResponse(BaseModel):
    task_id: str = Field()
    bindings: list[Any] = Field(default_factory=list)
    credentials: list[WorkerGitlabCredentialItem] = Field(default_factory=list)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerProgressRequest(BaseModel):
    worker_id: str = Field()
    task_id: str | None = Field(default=None)
    run_id: str | None = Field(default=None)
    current_stage: str | None = Field(default=None)
    stage_status: str | None = Field(default=None)
    config_json: Any | None = Field(default=None)
    result_yaml: str | None = Field(default=None)
    output_yaml: str | None = Field(default=None)
    result_summary_json: Any | None = Field(default=None)
    error_message: str | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    _accept_config_json = field_validator("config_json", mode="before")(accept_worker_json_text)
    _parse_result_summary_json = field_validator("result_summary_json", mode="before")(
        accept_worker_json_text
    )


class WorkerTaskEventRequest(BaseModel):
    worker_id: str = Field()
    task_id: str | None = Field(default=None)
    run_id: str | None = Field(default=None)
    collection_run_id: str | None = Field(default=None)
    collection_id: str | None = Field(default=None)
    case_id: str | None = Field(default=None)
    started_at: str | None = Field(default=None)
    heartbeat_at: str | None = Field(default=None)
    finished_at: str | None = Field(default=None)
    status: str | None = None
    success: bool | None = None
    error_message: str | None = Field(default=None)
    remediation: str | None = None
    duration_ms: int | None = Field(default=None)
    snapshot_json: Any | None = Field(default=None)
    step_results: list[Any] | None = Field(default=None)
    request: Any | None = None
    response: Any | None = None
    runtime_vars_json: Any | None = Field(default=None)
    extract_results: list[Any] | None = Field(default=None)
    assert_results: list[Any] | None = Field(default=None)
    config_json: Any | None = Field(default=None)
    result_yaml: str | None = Field(default=None)
    output_yaml: str | None = Field(default=None)
    result_summary_json: Any | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    _parse_snapshot_json = field_validator("snapshot_json", mode="before")(parse_json_object)
    _parse_runtime_vars_json = field_validator("runtime_vars_json", mode="before")(
        parse_json_object
    )
    _accept_config_json = field_validator("config_json", mode="before")(accept_worker_json_text)
    _accept_result_summary_json = field_validator("result_summary_json", mode="before")(
        accept_worker_json_text
    )
