"""Pure AI task kinds and stage transitions, independent of persistence and HTTP."""

AUXILIARY_EXECUTION_TYPES = frozenset(
    {
        "code_risk_analysis",
        "repository_profile",
        "test_report_generate",
        "test_order_graph",
        "test_order_case_visualization",
    }
)


def task_type_for(kind: str) -> str:
    if kind == "test_order_case_visualization":
        return kind
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
    if kind == "repository_profile":
        return "repository_profile"
    return "api_case_generate"


REVISION_ATTACHMENTS_FIELD = "revisionAttachments"


DEFAULT_FUNCTION_CASE_MODULE = "未分组"
