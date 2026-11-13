"""Strict contracts for newly generated functional artifacts (not legacy inputs)."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

Text = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


def reject(loc, message, value):
    raise ValidationError.from_exception_data(
        "Output",
        [
            {
                "type": "value_error",
                "loc": loc,
                "input": value,
                "ctx": {"error": ValueError(message)},
            }
        ],
    )


class ScopeEntry(Contract):
    id: Text
    sourceBlockIds: list[Text]
    basisStatus: Literal["confirmed", "inferred", "unconfirmed"]

    @model_validator(mode="after")
    def source_required(self):
        if len(self.sourceBlockIds) != len(set(self.sourceBlockIds)):
            raise ValueError("duplicate sourceBlockIds")
        if self.basisStatus != "unconfirmed" and not self.sourceBlockIds:
            raise ValueError("confirmed and inferred entries require sourceBlockIds")
        return self


class ScopeObject(ScopeEntry):
    name: Text
    type: Text
    description: Text


class ScopeImpact(ScopeEntry):
    testObjectIds: list[Text]
    area: Text
    impact: Text


class ScopeRisk(ScopeEntry):
    testObjectIds: list[Text]
    impactAreaIds: list[Text]
    description: Text


class ScopeQuestion(Contract):
    id: Text
    question: Text
    testObjectIds: list[Text]
    impactAreaIds: list[Text]
    riskIds: list[Text]
    sourceBlockIds: list[Text]
    sourceQuestionIds: list[Text]


class TestScopeAnalysisOutput(Contract):
    schemaVersion: Literal["1.0"]
    artifactType: Literal["test_scope_impact_risk"]
    testObjects: list[ScopeObject]
    impactAreas: list[ScopeImpact]
    risks: list[ScopeRisk]
    openQuestions: list[ScopeQuestion]

    @model_validator(mode="after")
    def references(self):
        groups = {
            name: getattr(self, name)
            for name in ("testObjects", "impactAreas", "risks", "openQuestions")
        }
        ids = {}
        for name, entries in groups.items():
            values = [entry.id for entry in entries]
            if len(values) != len(set(values)):
                raise ValueError(f"{name}: duplicate IDs")
            ids[name] = set(values)
        for name, entries in groups.items():
            for entry in entries:
                for field, target in (
                    ("testObjectIds", "testObjects"),
                    ("impactAreaIds", "impactAreas"),
                    ("riskIds", "risks"),
                ):
                    refs = getattr(entry, field, [])
                    if len(refs) != len(set(refs)) or not set(refs) <= ids[target]:
                        raise ValueError(f"{name}/{entry.id}: invalid {field}")
                for field in ("sourceBlockIds", "sourceQuestionIds"):
                    refs = getattr(entry, field, [])
                    if len(refs) != len(set(refs)):
                        raise ValueError(f"{name}/{entry.id}: duplicate {field}")
        return self


class TraceableReviewIssue(Contract):
    kind: Literal["unsupported", "missing", "granularity", "classification"]
    targetType: Literal["testPoint", "coverageGap", "missing"]
    targetId: str | None
    issue: Text
    suggestion: Text
    materialBlockIds: list[Text]
    testObjectIds: list[Text]
    impactAreaIds: list[Text]
    riskIds: list[Text]
    materialQuestionIds: list[Text]
    scopeQuestionIds: list[Text]


class TraceableReview(Contract):
    issues: list[TraceableReviewIssue]


class GeneratedCase(Contract):
    # Accepted so a model that echoes an ID is not repaired, but never kept: identity is
    # issued by `case_ids.assign_case_ids` after validation.
    case_id: str | None = Field(default=None, exclude=True)
    case_module: Text
    case_title: Text
    case_type: Literal[
        "功能测试",
        "性能测试",
        "配置相关",
        "安装部署",
        "安全测试",
        "接口测试",
        "单元测试",
        "其他",
        "异常测试",
        "兼容性测试",
        "升级测试",
        "资料测试",
        "可靠性测试",
        "易用性/体验测试",
        "规格一致性测试",
        "长稳测试",
        "可维/可服测试",
    ]
    priority: Literal["1", "2", "3", "4"]
    precondition: list[Text]
    test_steps: Annotated[list[Text], Field(min_length=1)]
    expected_results: Annotated[list[Text], Field(min_length=1)]

    @field_validator("precondition", "test_steps", "expected_results")
    @classmethod
    def numbering(cls, value):
        for i, line in enumerate(value, 1):
            if not line.startswith(f"{i}. ") or not line[len(f"{i}. ") :].strip():
                raise ValueError(f"item {i - 1} must start with '{i}. ' followed by content")
        return value

    @model_validator(mode="after")
    def paired_steps(self):
        if len(self.test_steps) != len(self.expected_results):
            reject(
                ("expected_results",),
                "test_steps and expected_results must have equal lengths",
                self.expected_results,
            )
        return self


class DetailedCasesOutput(Contract):
    cases: list[GeneratedCase]

    @model_validator(mode="after")
    def duplicates(self):
        seen = set()
        for i, case in enumerate(self.cases):
            key = (
                case.case_module.strip().casefold(),
                case.case_title.strip().casefold(),
            )
            if key in seen:
                reject(
                    ("cases", i, "case_title"),
                    f"duplicate module/title {key}",
                    case.case_title,
                )
            seen.add(key)
        return self


class MainPath(Contract):
    path_id: Text
    case_ids: Annotated[list[Text], Field(min_length=2)]


class RelationEdge(Contract):
    edge_id: Text
    from_case_id: Text
    to_case_id: Text
    relation_type: Literal["next", "branch"]
    order: Annotated[int, Field(gt=0)]


class RelationAnalysisOutput(Contract):
    schema_version: Literal["2.0"]
    main_paths: list[MainPath]
    edges: list[RelationEdge]

    @model_validator(mode="after")
    def graph_structure(self):
        path_ids = [path.path_id for path in self.main_paths]
        if len(path_ids) != len(set(path_ids)):
            reject(("main_paths",), "path_id 重复", path_ids)
        sequences: set[tuple[str, ...]] = set()
        for index, path in enumerate(self.main_paths):
            if len(path.case_ids) != len(set(path.case_ids)):
                reject(
                    ("main_paths", index, "case_ids"),
                    "主骨内 case_id 重复",
                    path.case_ids,
                )
            sequence = tuple(path.case_ids)
            if sequence in sequences:
                reject(
                    ("main_paths", index),
                    "重复输出完全相同的主骨序列",
                    path.case_ids,
                )
            sequences.add(sequence)
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            reject(("edges",), "edge_id 重复", edge_ids)
        directed_pairs: set[tuple[str, str]] = set()
        next_pairs: set[tuple[str, str]] = set()
        source_orders: set[tuple[str, int]] = set()
        for index, edge in enumerate(self.edges):
            if edge.from_case_id == edge.to_case_id:
                reject(("edges", index), "不允许自环", edge.edge_id)
            pair = (edge.from_case_id, edge.to_case_id)
            if pair in directed_pairs:
                reject(("edges", index), "同一有向端点对只允许一条边", pair)
            directed_pairs.add(pair)
            source_order = (edge.from_case_id, edge.order)
            if source_order in source_orders:
                reject(
                    ("edges", index, "order"),
                    "同一起点的出线 order 重复",
                    edge.order,
                )
            source_orders.add(source_order)
            if edge.relation_type == "next":
                next_pairs.add(pair)
        for index, path in enumerate(self.main_paths):
            for previous, current in zip(path.case_ids, path.case_ids[1:]):
                if (previous, current) not in next_pairs:
                    reject(
                        ("main_paths", index, "case_ids"),
                        "主骨相邻用例必须有同方向的 next 边",
                        [previous, current],
                    )
        return self


CONTRACTS = {
    "requirement_analysis": TestScopeAnalysisOutput,
    "traceable_case_audit": TraceableReview,
    "detailed_cases": DetailedCasesOutput,
    "relation_analysis": RelationAnalysisOutput,
}
