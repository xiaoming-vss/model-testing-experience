"""Track explicit confirmation citations within this invocation, never across runs.

This checks provenance coverage, not whether prose correctly implements a decision.
"""

from typing import Any, NotRequired, TypedDict


class ConfirmationReference(TypedDict):
    sourceId: str
    locator: str
    inputStatements: NotRequired[list[str]]


def collect_confirmation_references(
    *artifacts: dict[str, Any],
) -> list[ConfirmationReference]:
    """Collect used user-confirmation citations from already validated input artifacts."""
    collected: dict[tuple[str, str], ConfirmationReference] = {}
    for artifact in artifacts:
        sources = {s["id"] for s in artifact["sources"] if s["type"] == "user_confirmation"}
        if artifact["artifactType"] == "readable_requirement_material":
            blocks = {b["id"]: b for b in artifact["materialBlocks"]}
            business_items = [
                item
                for function in artifact["functions"]
                for section in function["sections"]
                for item in section["items"]
            ] + artifact["questions"]
            for item in business_items:
                for block_id in item["materialBlockIds"]:
                    block = blocks.get(block_id)
                    if block is None or block["sourceId"] not in sources:
                        continue
                    key = (block["sourceId"], block["locator"])
                    entry = collected.setdefault(key, {"sourceId": key[0], "locator": key[1]})
                    statement = block["content"].get("text")
                    if isinstance(statement, str) and statement:
                        statements = entry.setdefault("inputStatements", [])
                        if statement not in statements:
                            statements.append(statement)
            continue
    return list(collected.values())


class ConfirmationCoverageError(ValueError):
    """Keep business content in repair context, out of the public error summary."""

    def __init__(self, message: str, repair_context: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.repair_context = repair_context


def validate_confirmation_coverage(
    artifact: dict[str, Any], required: list[ConfirmationReference]
) -> None:
    """Reject omitted/unused confirmation citations after schema/reference validation."""
    coverage_artifact = artifact
    if artifact["artifactType"] == "document_extraction":
        # Raw material preserves provenance; only facts/questions carry its business disposition.
        coverage_artifact = {**artifact, "contentBlocks": []}
    used = {
        (ref["sourceId"], ref["locator"])
        for ref in collect_confirmation_references(coverage_artifact)
    }
    missing = [ref for ref in required if (ref["sourceId"], ref["locator"]) not in used]
    if missing:
        locations = "；".join(f"{ref['sourceId']} / {ref['locator']}" for ref in missing)
        context = []
        for ref in missing:
            matches = [
                e["id"]
                for e in artifact.get("evidence", [])
                if e["sourceId"] == ref["sourceId"] and e["locator"] == ref["locator"]
            ]
            context.append(
                {
                    "sourceId": ref["sourceId"],
                    "locator": ref["locator"],
                    "inputStatements": ref.get("inputStatements", []),
                    "existingEvidenceIds": matches,
                    "issue": "证据已登记但正文未引用或来源类型不正确"
                    if matches
                    else "未找到匹配的证据定位",
                    "repair": "核对相关规则并落实输入结论；存在歧义则保留局部问题。不能仅挂引用，不能臆造业务结论。",
                }
            )
        raise ConfirmationCoverageError(
            f"确认来源未承接到业务内容或剩余问题：{locations}。"
            "保留输入中的来源 ID 和定位，并核对结论及影响；仅登记来源、原文块或未引用的 evidence 不算承接。",
            context,
        )
