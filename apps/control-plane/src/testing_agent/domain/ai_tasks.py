"""Pure AI task kinds and stage transitions, independent of persistence and HTTP."""


def task_type_for(kind: str) -> str:
    if kind == "ui":
        return "ui_case_generate"
    if kind == "function":
        return "functional_case_generate"
    if kind == "requirement_analysis":
        return "requirement_analysis"
    if kind == "test_report":
        return "test_report_generate"
    if kind == "test_order_graph":
        return "test_order_graph"
    if kind == "code_risk_analysis":
        return "code_risk_analysis"
    return "api_case_generate"


FUNCTION_CASE_REVIEWABLE_STAGES = {"requirement_analysis", "case_names"}


FUNCTION_CASE_REVIEW_READY_STATUSES = {"waiting_review", "saved"}


FUNCTION_CASE_NEXT_STAGE = {
    "requirement_analysis": "case_names",
    "case_names": "detailed_cases",
}


FUNCTION_CASE_RELATION_STAGE = "relation_analysis"


FUNCTION_CASE_RELATION_DISPATCH_STATUSES = {"pending", "claimed", "running"}


REQUIREMENT_ANALYSIS_INITIAL_STAGE = "extracting_text"


REQUIREMENT_ANALYSIS_FINAL_STAGE = "feature_understanding"


# completed is the common terminal marker, not a third requirement-analysis stage.
REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES = {REQUIREMENT_ANALYSIS_FINAL_STAGE, "completed"}


REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES = {"extracting_text"}


REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES = {"waiting_review", "saved"}


REQUIREMENT_ANALYSIS_NEXT_STAGE = {
    "extracting_text": "feature_understanding",
}


REVISION_INSTRUCTION_FIELD = "revisionInstruction"


DEFAULT_FUNCTION_CASE_MODULE = "未分组"


def next_function_case_stage(stage: str) -> str | None:
    return FUNCTION_CASE_NEXT_STAGE.get(stage)


def next_requirement_analysis_stage(stage: str) -> str | None:
    return REQUIREMENT_ANALYSIS_NEXT_STAGE.get(stage)
