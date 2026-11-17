"""Strict run-specification contracts."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from ..core.errors import SpecError

SUPPORTED_SPEC_VERSIONS = frozenset({"1.0"})

_RESERVED_ENV_NAMES = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "PWD",
        "PYTHONHOME",
        "PYTHONPATH",
        "SHELL",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USER",
    }
)
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DATA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class WireModel(BaseModel):
    """Base model using camelCase wire names and rejecting unknown fields."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ContentType(StrEnum):
    JSON = "json"
    FORM = "form"
    TEXT = "text"
    NONE = "none"


class FailurePolicy(StrEnum):
    ABORT_ITERATION = "abort_iteration"
    CONTINUE = "continue"
    ABORT_TEST = "abort_test"


class CheckType(StrEnum):
    STATUS = "status"
    JSON = "json"
    HEADER = "header"
    BODY = "body"


class CheckOp(StrEnum):
    EQ = "eq"
    NE = "ne"
    EXISTS = "exists"
    REGEX = "regex"
    CONTAINS = "contains"
    IN = "in"
    GTE = "gte"
    LTE = "lte"


class ExtractSource(StrEnum):
    JSON = "json"
    HEADER = "header"
    REGEX = "regex"


class DataStrategy(StrEnum):
    UNIQUE_PER_ITERATION = "unique_per_iteration"
    PER_VU = "per_vu"
    RANDOM = "random"
    CYCLE = "cycle"


class ExhaustedPolicy(StrEnum):
    CYCLE = "cycle"
    FAIL = "fail"


class AcceptanceSource(StrEnum):
    USER_CONFIRMED = "user_confirmed"
    MODEL_SUGGESTED = "model_suggested"
    MISSING = "missing"


class CheckSpec(WireModel):
    type: CheckType
    op: CheckOp = CheckOp.EQ
    path: str = ""
    name: str = ""
    pattern: str = ""
    value: Any = None

    @model_validator(mode="after")
    def _validate_fields(self) -> Self:
        if self.type is CheckType.JSON and not self.path.strip():
            raise ValueError("json 校验必须提供 path")
        if self.type is CheckType.HEADER and not self.name.strip():
            raise ValueError("header 校验必须提供 name")
        if self.type is CheckType.STATUS and not isinstance(self.value, int):
            raise ValueError("status 校验必须提供整数 value")
        if (
            self.type is CheckType.BODY
            and self.op
            in {
                CheckOp.REGEX,
                CheckOp.CONTAINS,
            }
            and not self.pattern
        ):
            raise ValueError("body 的 regex/contains 校验必须提供 pattern")
        if self.op is CheckOp.REGEX and not self.pattern:
            raise ValueError("regex 校验必须提供 pattern")
        return self


class ExtractSpec(WireModel):
    name: str
    source: ExtractSource = Field(default=ExtractSource.JSON, alias="from")
    path: str = ""
    pattern: str = ""
    group: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def _validate_fields(self) -> Self:
        if not self.name.strip():
            raise ValueError("提取变量名不能为空")
        if self.source is ExtractSource.JSON and not self.path.strip():
            raise ValueError("json 提取必须提供 path")
        if self.source is ExtractSource.HEADER and not self.path.strip():
            raise ValueError("header 提取必须提供 path 作为响应头名称")
        if self.source is ExtractSource.REGEX and not self.pattern:
            raise ValueError("regex 提取必须提供 pattern")
        return self


class StepSpec(WireModel):
    name: str
    method: HttpMethod = HttpMethod.GET
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    content_type: ContentType = ContentType.JSON
    checks: list[CheckSpec] = Field(default_factory=list)
    extract: list[ExtractSpec] = Field(default_factory=list)
    on_failure: FailurePolicy = FailurePolicy.ABORT_ITERATION
    think_time_ms: int = Field(default=0, ge=0)

    @field_validator("name", "path")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value


class VusLoad(WireModel):
    model: Literal["vus"] = "vus"
    vus: int = Field(ge=1)
    duration: str
    ramp_up: str = ""
    ramp_down: str = ""

    @field_validator("duration", "ramp_up", "ramp_down")
    @classmethod
    def _valid_duration(cls, value: str) -> str:
        if value and not value.strip():
            raise ValueError("duration 不能为空白")
        return value

    @model_validator(mode="after")
    def _paired_ramp(self) -> Self:
        if bool(self.ramp_up) != bool(self.ramp_down):
            raise ValueError("ramp_up 和 ramp_down 必须同时提供或同时省略")
        if not self.duration.strip():
            raise ValueError("duration 不能为空")
        return self


class ArrivalRateLoad(WireModel):
    model: Literal["arrival_rate"] = "arrival_rate"
    rate: int = Field(ge=1)
    time_unit: str = "1s"
    duration: str
    pre_allocated_vus: int = Field(default=1, ge=1, alias="preAllocatedVUs")
    max_vus: int = Field(default=10, ge=1, alias="maxVUs")

    @field_validator("time_unit", "duration")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value

    @model_validator(mode="after")
    def _max_vus(self) -> Self:
        if self.max_vus < self.pre_allocated_vus:
            raise ValueError("max_vus 不能小于 pre_allocated_vus")
        return self


class RequestRateLoad(WireModel):
    model: Literal["request_rate"] = "request_rate"
    rate: int = Field(ge=1)
    time_unit: str = "1s"
    duration: str
    pre_allocated_vus: int = Field(default=1, ge=1, alias="preAllocatedVUs")
    max_vus: int = Field(default=10, ge=1, alias="maxVUs")

    @field_validator("time_unit", "duration")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value

    @model_validator(mode="after")
    def _max_vus(self) -> Self:
        if self.max_vus < self.pre_allocated_vus:
            raise ValueError("max_vus 不能小于 pre_allocated_vus")
        return self


LoadSpec = Annotated[
    VusLoad | ArrivalRateLoad | RequestRateLoad,
    Field(discriminator="model"),
]


class DataSpec(WireModel):
    name: str
    source: str = ""
    rows: list[dict[str, str]] | None = None
    strategy: DataStrategy = DataStrategy.UNIQUE_PER_ITERATION
    on_exhausted: ExhaustedPolicy = ExhaustedPolicy.CYCLE
    format: Literal["csv", "json"] | None = None

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        if not _DATA_NAME_RE.fullmatch(value):
            raise ValueError("数据名只能包含字母、数字、下划线和连字符，且以字母或下划线开头")
        return value

    @model_validator(mode="after")
    def _source_or_rows(self) -> Self:
        if bool(self.source) == bool(self.rows):
            raise ValueError("source 和 rows 必须二选一")
        if self.rows is not None and not self.rows:
            raise ValueError("rows 不能为空")
        return self


class AcceptanceSpec(WireModel):
    source: AcceptanceSource
    confirmed: bool = False
    criteria: dict[str, list[str]] = Field(default_factory=dict)
    note: str = ""

    @model_validator(mode="after")
    def _source_rules(self) -> Self:
        if self.source is AcceptanceSource.USER_CONFIRMED:
            if not self.confirmed:
                raise ValueError("user_confirmed 必须标记 confirmed=true")
            if not self.criteria:
                raise ValueError("user_confirmed 必须提供验收标准")
        elif self.source is AcceptanceSource.MODEL_SUGGESTED:
            if self.confirmed:
                raise ValueError("model_suggested 不能标记 confirmed=true")
        else:
            if self.confirmed:
                raise ValueError("missing 不能标记 confirmed=true")
            if self.criteria:
                raise ValueError("missing 不能包含验收标准")

        for metric, expressions in self.criteria.items():
            if not metric.strip():
                raise ValueError("验收标准指标名不能为空")
            if not expressions:
                raise ValueError(f"验收标准 {metric} 不能为空")
            for expression in expressions:
                if not expression.strip():
                    raise ValueError(f"验收标准 {metric} 包含空表达式")
        return self


class EnvironmentSpec(WireModel):
    base_url: str
    variables: dict[str, str] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def _valid_base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("base_url 必须是 http(s) URL")
        if parts.username or parts.password:
            raise ValueError("base_url 不能包含凭据")
        if parts.query or parts.fragment:
            raise ValueError("base_url 不能包含查询或片段")
        return value.rstrip("/")

    @field_validator("variables")
    @classmethod
    def _valid_variables(cls, value: dict[str, str]) -> dict[str, str]:
        for name, variable_value in value.items():
            if not _ENV_NAME_RE.fullmatch(name):
                raise ValueError(f"环境变量名不合法: {name}")
            if name.startswith("K6_") or name in _RESERVED_ENV_NAMES:
                raise ValueError(f"环境变量名保留，不能使用: {name}")
            if not isinstance(variable_value, str):
                raise ValueError(f"环境变量 {name} 的值必须是字符串")
        return value


class RemoteWriteAuth(WireModel):
    type: Literal["none", "basic", "bearer", "headers"] = "none"
    username: str = ""
    password: SecretStr = SecretStr("")
    token: SecretStr = SecretStr("")
    headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _auth_fields(self) -> Self:
        if self.type == "basic":
            if not self.username.strip():
                raise ValueError("basic 认证必须提供 username")
        elif self.type == "bearer":
            if not self.token.get_secret_value():
                raise ValueError("bearer 认证必须提供 token")
        elif self.type == "headers":
            if not self.headers:
                raise ValueError("headers 认证必须提供 headers")
        else:
            if self.headers:
                raise ValueError("none 认证不能提供 headers")
        return self


class RemoteWriteSpec(WireModel):
    url: str
    auth: RemoteWriteAuth = Field(default_factory=RemoteWriteAuth)
    push_interval: str = "5s"
    trend_stats: str = "p(95),p(99),avg,min,max"

    @field_validator("url")
    @classmethod
    def _valid_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("Remote Write URL 必须是 http(s) URL")
        if parts.username or parts.password:
            raise ValueError("Remote Write URL 不能包含凭据")
        return value

    @field_validator("push_interval", "trend_stats")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value


class Limits(WireModel):
    max_duration_seconds: int = Field(default=3600, ge=1, le=86400)
    stop_grace_seconds: int = Field(default=30, ge=1, le=600)


class CaseSpec(WireModel):
    name: str
    steps: list[StepSpec]
    load: LoadSpec
    acceptance: AcceptanceSpec
    data: list[DataSpec] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _non_blank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("用例名不能为空")
        return value

    @model_validator(mode="after")
    def _validate_case(self) -> Self:
        if not self.steps:
            raise ValueError("用例至少需要一个步骤")

        step_names = [step.name for step in self.steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("步骤名称必须唯一")

        data_names = [data.name for data in self.data]
        if len(data_names) != len(set(data_names)):
            raise ValueError("数据名必须唯一")

        for step in self.steps:
            extract_names = [item.name for item in step.extract]
            if len(extract_names) != len(set(extract_names)):
                raise ValueError(f"步骤 {step.name} 的提取变量名必须唯一")

        if isinstance(self.load, RequestRateLoad) and len(self.steps) != 1:
            raise ValueError("request_rate 只支持单步骤迭代；多步骤请使用 arrival_rate 或 vus")
        return self


class RunSpec(WireModel):
    spec_version: str
    run_id: str
    project_id: str = ""
    case: CaseSpec
    environment: EnvironmentSpec
    remote_write: RemoteWriteSpec
    limits: Limits = Field(default_factory=Limits)

    @field_validator("spec_version")
    @classmethod
    def _supported_version(cls, value: str) -> str:
        if value not in SUPPORTED_SPEC_VERSIONS:
            supported = ", ".join(sorted(SUPPORTED_SPEC_VERSIONS))
            raise ValueError(f"不支持的 specVersion: {value}；支持 {supported}")
        return value

    @field_validator("run_id")
    @classmethod
    def _non_blank_run_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("runId 不能为空")
        return value


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[Any, Any]:
        if isinstance(node, yaml.MappingNode):
            self.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, (dict, list, set)):
                raise SpecError("YAML 映射键必须是标量")
            if key in mapping:
                raise SpecError(f"YAML 重复键: {key}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _object_pairs_without_duplicates(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SpecError(f"JSON 重复键: {key}")
        result[key] = value
    return result


def load_run_spec(path: str | Path) -> RunSpec:
    """Load a run specification from JSON or YAML and validate it."""

    spec_path = Path(path)
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"无法读取运行规格: {spec_path}") from exc

    suffix = spec_path.suffix.lower()
    try:
        if suffix in {".yaml", ".yml"}:
            data = yaml.load(text, Loader=_UniqueKeyLoader)
        elif suffix == ".json":
            data = json.loads(text, object_pairs_hook=_object_pairs_without_duplicates)
        else:
            raise SpecError("运行规格必须是 .json、.yaml 或 .yml 文件")
    except SpecError:
        raise
    except yaml.YAMLError as exc:
        raise SpecError(f"YAML 解析失败: {exc}") from None
    except json.JSONDecodeError as exc:
        raise SpecError(f"JSON 解析失败: {exc}") from None

    if not isinstance(data, dict):
        raise SpecError("运行规格顶层必须是对象")

    try:
        return RunSpec.model_validate(data)
    except ValidationError as exc:
        raise SpecError(f"运行规格校验失败: {_format_validation_error(exc)}") from None


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors(include_url=False, include_input=False):
        location = ".".join(str(item) for item in error["loc"])
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts) or "unknown"
