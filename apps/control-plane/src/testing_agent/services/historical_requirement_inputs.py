"""Build a compact, immutable input for historical requirement analysis."""

# transaction-bound: retrieve evidence in the same transaction as the frozen stage input.

import json
import re
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.domain.historical_requirement_artifacts import validate_historical_input
from testing_agent.domain.requirement_artifacts import validate_artifact
from testing_agent.repositories.historical_requirement_materials import (
    iter_project_materials,
    read_adopted_relation_results,
)
from testing_agent.services.generation_source_selection import ResolvedRunSources

MATCHES_PER_FUNCTION = 5
PRIMARY_SECTIONS = {"功能使用与业务规则", "完整业务流程"}
RULE_RELATIONS = {
    "still_applies": "depends_on",
    "supplemented": "supplements",
    "changed": "changes",
    "replaced": "replaces",
    "retired": "changes",
}


def _items(functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for f_index, function in enumerate(functions, 1):
        sections = function["sections"]
        primary = any(section["title"] in PRIMARY_SECTIONS for section in sections)
        for s_index, section in enumerate(sections, 1):
            if primary and section["title"] not in PRIMARY_SECTIONS:
                continue
            for i_index, item in enumerate(section["items"], 1):
                result.append(
                    {
                        "itemId": f"{f_index}-{s_index}-{i_index}",
                        "functionId": function["id"],
                        "functionName": function["name"],
                        "sectionTitle": section["title"],
                        "text": item["text"],
                        "status": item["status"],
                        "materialBlockIds": item["materialBlockIds"],
                    }
                )
    return result


def historical_search_terms(text: str) -> set[str]:
    """Build comparable words and Chinese bigrams for historical retrieval."""
    terms: set[str] = set()
    for word in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.casefold()):
        if "\u3400" <= word[0] <= "\u9fff":
            terms.update(word[i : i + 2] for i in range(len(word) - 1))
        else:
            terms.add(word)
    return terms


def _confirmed_edges(contents: list[str]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for content in contents:
        result = json.loads(content)
        for relation in result["relations"]:
            for impact in relation["impacts"]:
                if impact["reviewStatus"] == "proposed":
                    edges.append(
                        {
                            "fromRequirementId": result["requirementId"],
                            "fromMaterialSnapshotId": result["materialSnapshotId"],
                            "toRequirementId": relation["historicalRequirementId"],
                            "toMaterialSnapshotId": relation["historicalMaterialSnapshotId"],
                            "relationType": RULE_RELATIONS[impact["ruleEffect"]],
                            "scope": impact["scope"],
                        }
                    )
    return edges


async def build_historical_requirement_input(
    session: AsyncSession,
    *,
    project_id: str,
    requirement_id: str,
    sources: ResolvedRunSources,
) -> dict[str, Any]:
    """Shortlist material evidence; only this compact projection is sent to the model."""
    material = next(
        (item for item in sources.selected_content if item.stage == "extracting_text"), None
    )
    selected = next(
        (item for item in sources.manifest.selected_sources if item.stage == "extracting_text"),
        None,
    )
    if material is None or selected is None or selected.source_kind != "current":
        raise SourceClosureError("pending_upstream")
    try:
        current = {
            "requirementId": requirement_id,
            "materialSnapshotId": selected.snapshot_id,
            "items": _items(
                validate_artifact(material.content, "document_extraction")["functions"]
            ),
        }
        history = await _shortlist(session, project_id=project_id, current=current)
        versions = {
            item["requirementId"]: item["materialSnapshotId"] for item in [current, *history]
        }
        known = []
        if history:
            results = await read_adopted_relation_results(
                session, project_id=project_id, requirement_ids=set(versions)
            )
            for edge in _confirmed_edges(results):
                if (
                    all(
                        versions.get(edge[f"{side}RequirementId"])
                        == edge[f"{side}MaterialSnapshotId"]
                        for side in ("from", "to")
                    )
                    and edge not in known
                ):
                    known.append(edge)
        return validate_historical_input(
            {
                "schemaVersion": "0.1",
                "artifactType": "historical_requirement_relation_input",
                "currentRequirement": current,
                "historicalRequirements": history,
                "knownRelations": known,
            }
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise SourceClosureError("source_unknown") from exc


async def _shortlist(
    session: AsyncSession, *, project_id: str, current: dict[str, Any]
) -> list[dict[str, Any]]:
    requirement_id = current["requirementId"]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in current["items"]:
        groups[item["functionId"]].append(item)
    queries = [
        (items[0]["functionName"], " ".join(item["text"] for item in items))
        for items in groups.values()
    ]
    terms = [historical_search_terms(f"{name} {body}") for name, body in queries]
    prior = await read_adopted_relation_results(
        session, project_id=project_id, requirement_ids={requirement_id}
    )
    preferred = {edge["toRequirementId"] for edge in _confirmed_edges(prior)}
    matches: list[list[tuple[int, str, str, dict[str, Any]]]] = [[] for _ in queries]
    async for row in iter_project_materials(
        session, project_id=project_id, current_requirement_id=requirement_id
    ):
        if not row.functions:
            continue
        historical = json.loads(row.functions) if isinstance(row.functions, str) else row.functions
        if not isinstance(historical, list):
            continue
        for item in _items(historical):
            item_terms = historical_search_terms(f"{item['functionName']} {item['text']}")
            for index, (name, body) in enumerate(queries):
                overlap = len(terms[index] & item_terms)
                explicit = row.requirement_id in body
                if not overlap and not explicit:
                    continue
                score = overlap + 8 * (item["functionName"] == name)
                score += 1000 * explicit + 100 * (row.requirement_id in preferred)
                bucket = matches[index]
                bucket.append((score, row.requirement_id, row.snapshot_id, item))
                bucket.sort(key=lambda match: match[0], reverse=True)
                del bucket[MATCHES_PER_FUNCTION:]

    history: dict[str, dict[str, Any]] = {}
    for bucket in matches:
        for _, requirement_id, snapshot_id, item in bucket:
            entry = history.setdefault(
                requirement_id,
                {"requirementId": requirement_id, "materialSnapshotId": snapshot_id, "items": []},
            )
            if item not in entry["items"]:
                entry["items"].append(item)
    return list(history.values())
