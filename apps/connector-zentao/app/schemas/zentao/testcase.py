from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.zentao.imports import (
    first_value,
    normalize_bool,
    normalize_datetime,
    normalize_optional_int,
    normalize_optional_str,
    normalize_priority,
    normalize_required_int,
    normalize_required_str,
)


class TestCaseImportData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    module: str | None = None
    title: str
    preconditions: str | None = None
    steps: str | None = None
    expectedResults: str | None = None
    priority: str | None = None
    caseType: str | None = None
    status: str | None = None
    lastRunDate: str | None = None
    lastRunResult: str | None = None
    orderNo: int | None = None
    deleted: bool = False

    @classmethod
    def from_upstream(
        cls,
        testcase_list_item: dict[str, Any],
        testcase_detail: dict[str, Any],
        *,
        order_no: int | None = None,
    ) -> "TestCaseImportData":
        steps_text, expected_results_text = normalize_case_steps(testcase_detail.get("steps"))
        return cls(
            id=str(normalize_required_int(testcase_detail.get("id"))),
            module=normalize_optional_str(first_value(testcase_detail, "moduleName", "module")),
            title=normalize_required_str(testcase_detail.get("title")),
            preconditions=normalize_optional_str(
                first_value(testcase_detail, "preconditions", "precondition")
            ),
            steps=steps_text,
            expectedResults=expected_results_text
            or normalize_optional_str(
                first_value(testcase_detail, "expectedResults", "expected", "expect")
            ),
            priority=normalize_priority(first_value(testcase_detail, "priority", "pri")),
            caseType=normalize_optional_str(first_value(testcase_detail, "caseType", "type")),
            status=normalize_optional_str(testcase_list_item.get("status")),
            lastRunDate=normalize_datetime(
                first_value(testcase_list_item, "lastRunDate", "last_run_date")
            ),
            lastRunResult=normalize_optional_str(
                first_value(testcase_list_item, "lastRunResult", "last_run_result")
            ),
            orderNo=order_no,
            deleted=normalize_bool(testcase_detail.get("deleted")),
        )


class TestCaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    module: int = Field(default=0, ge=0)
    story: int = Field(default=0, ge=0)
    pri: int = Field(default=3, ge=1, le=4)
    precondition: str = ""
    steps: list[str] = Field(min_length=1)
    expects: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_step_fields(self) -> "TestCaseCreateRequest":
        step_count = len(self.steps)
        if len(self.expects) != step_count:
            raise ValueError("steps and expects must have the same length.")
        return self

    def to_zentao_payload(
        self,
        *,
        product_id: int,
        project: int,
        execution: int,
    ) -> dict[str, Any]:
        payload = self.model_dump()
        payload["productID"] = product_id
        payload["project"] = project
        payload["execution"] = execution
        payload["stepType"] = ["step"] * len(self.steps)
        return payload


class TestCaseBatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    productID: int = Field(ge=1)
    project: int = Field(default=0, ge=0)
    execution: int = Field(default=0, ge=0)
    cases: list[TestCaseCreateRequest] = Field(min_length=1)

    def to_zentao_payloads(self) -> list[dict[str, Any]]:
        return [
            item.to_zentao_payload(
                product_id=self.productID,
                project=self.project,
                execution=self.execution,
            )
            for item in self.cases
        ]


class TestCaseCreateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    status: str = "success"

    @classmethod
    def from_upstream(cls, payload: dict[str, Any]) -> "TestCaseCreateData":
        return cls(
            id=normalize_required_int(payload.get("id")),
            status=normalize_required_str(payload.get("status")),
        )


class TestCaseBatchCreateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    items: list[TestCaseCreateData]


def extract_case_id(item: dict[str, Any]) -> int | None:
    return normalize_optional_int(first_value(item, "case", "caseID", "case_id", "id"))




def normalize_case_steps(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, str):
        return normalize_optional_str(value), None

    step_items = list(value.values()) if isinstance(value, dict) else value
    if not isinstance(step_items, list | tuple):
        return normalize_optional_str(step_items), None

    steps: list[str] = []
    expected_results: list[str] = []
    for index, item in enumerate(step_items, start=1):
        if not isinstance(item, dict):
            text = normalize_optional_str(item)
            if text:
                steps.append(f"{index}. {text}")
            continue

        step_text = normalize_optional_str(first_value(item, "desc", "step", "content", "actions"))
        expected_text = normalize_optional_str(
            first_value(item, "expect", "expected", "expectedResult")
        )
        if step_text:
            steps.append(f"{index}. {step_text}")
        if expected_text:
            expected_results.append(f"{index}. {expected_text}")

    return _join_lines(steps), _join_lines(expected_results)


def _join_lines(values: list[str]) -> str | None:
    return "\n".join(values) if values else None
