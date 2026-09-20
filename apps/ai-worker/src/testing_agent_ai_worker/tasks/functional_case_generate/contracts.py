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


class EntryPoint(Contract):
    function: str | None
    path: str | None
    action: str | None


class Overview(Contract):
    purpose: str | None
    applicableObjects: list[str]
    actors: list[str]
    entryPoints: list[EntryPoint]
    explicitExclusions: list[str]


class Factor(Contract):
    factorId: Annotated[str, StringConstraints(pattern=r"^F[0-9]{2,}$")]
    name: Text
    confirmedValues: list[str]
    defaultValue: str | int | float | bool | None
    clarificationNeeded: str | None


class Rule(Contract):
    ruleId: Annotated[str, StringConstraints(pattern=r"^R[0-9]{2,}$")]
    category: Text
    name: Text
    confirmationStatus: Literal["需求明确", "基于规则推导", "待确认"]
    applicableObject: str | None
    preconditions: list[str]
    trigger: str | None
    expectedBehavior: list[str]
    prohibitedOrSkippedBehavior: list[str]
    observableOutcome: str | None
    sourceReferences: list[str]
    relatedQuestionIds: list[str]


class Scenario(Contract):
    scenarioId: Annotated[str, StringConstraints(pattern=r"^S[0-9]{2,}$")]
    relatedRuleIds: Annotated[list[str], Field(min_length=1)]
    derivationType: Literal["需求直接描述", "基于规则推导"]
    conditions: list[str]
    trigger: str | None
    verificationObjective: str | None
    readyForTestPointGeneration: bool
    blockingReason: str | None
    relatedQuestionIds: list[str]

    @model_validator(mode="after")
    def readiness(self):
        if self.readyForTestPointGeneration:
            if (
                not self.verificationObjective
                or not self.verificationObjective.strip()
                or self.blockingReason is not None
            ):
                raise ValueError(
                    "readyForTestPointGeneration=true requires verificationObjective and blockingReason=null"
                )
        elif (
            not self.blockingReason
            or not self.blockingReason.strip()
            or not self.relatedQuestionIds
        ):
            raise ValueError(
                "readyForTestPointGeneration=false requires blockingReason and relatedQuestionIds"
            )
        return self


class Question(Contract):
    questionId: Annotated[str, StringConstraints(pattern=r"^Q[0-9]{2,}$")]
    question: Text
    affectedScope: str | None
    blockedWork: str | None


class RequirementAnalysisOutput(Contract):
    functionalOverview: Overview
    scenarioFactors: list[Factor]
    businessRules: list[Rule]
    scenarioBreakdown: list[Scenario]
    openQuestions: list[Question]

    @model_validator(mode="after")
    def references(self):
        for field, id_field in [
            ("scenarioFactors", "factorId"),
            ("businessRules", "ruleId"),
            ("scenarioBreakdown", "scenarioId"),
            ("openQuestions", "questionId"),
        ]:
            ids = [getattr(item, id_field) for item in getattr(self, field)]
            if len(ids) != len(set(ids)):
                reject((field,), f"{id_field}: duplicate IDs", ids)
        rules = {r.ruleId for r in self.businessRules}
        questions = {q.questionId for q in self.openQuestions}
        for field in ("businessRules", "scenarioBreakdown"):
            for i, item in enumerate(getattr(self, field)):
                if not set(item.relatedQuestionIds) <= questions:
                    reject(
                        (field, i, "relatedQuestionIds"),
                        "unknown question ID",
                        item.relatedQuestionIds,
                    )
        for i, item in enumerate(self.scenarioBreakdown):
            if not set(item.relatedRuleIds) <= rules:
                reject(
                    ("scenarioBreakdown", i, "relatedRuleIds"),
                    "unknown rule ID",
                    item.relatedRuleIds,
                )
        return self


class Point(Contract):
    case_name: Text


class Dimension(Contract):
    test_model: Text
    test_points: Annotated[list[Point], Field(min_length=1)]


class Category(Contract):
    data: Annotated[list[Dimension], Field(min_length=1)]
    model: Text


class TestPointsOutput(Contract):
    categories: list[Category]


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
    "requirement_analysis": RequirementAnalysisOutput,
    "case_names": TestPointsOutput,
    "detailed_cases": DetailedCasesOutput,
    "relation_analysis": RelationAnalysisOutput,
}
