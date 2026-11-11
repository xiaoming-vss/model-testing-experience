#!/usr/bin/env python3
"""Validate cumulative graph 2.0, source IDs and explicit historical changes."""
import argparse
import sys
from case_store import (ContractError, array, current_case_ids, emit, fields, load_request, read_json,
                        require, string_array, text_value)

RECOMMENDED_BATCH_SIZE = 30


def graph_index(graph, store):
    fields(graph, {"schema_version", "main_paths", "edges"}, "graph")
    require(graph["schema_version"] == "2.0", "schema_version must be the string 2.0")
    edges, pairs, orders = {}, {}, set()
    for edge in array(graph["edges"], "edges"):
        fields(edge, {"edge_id", "from_case_id", "to_case_id", "relation_type", "order"}, "edge")
        eid = text_value(edge["edge_id"], "edge_id")
        source = text_value(edge["from_case_id"], "from_case_id")
        target = text_value(edge["to_case_id"], "to_case_id")
        require(eid not in edges, "Duplicate edge_id: " + eid)
        require(source in store and target in store, "Edge references an unknown source case ID: " + eid)
        require(source != target, "Self edge is forbidden: " + eid)
        require(edge["relation_type"] in ("next", "branch"), "Invalid relation_type: " + eid)
        require(type(edge["order"]) is int and edge["order"] > 0, "order must be a positive integer: " + eid)
        require((source, target) not in pairs, "Duplicate directed endpoints: " + eid)
        require((source, edge["order"]) not in orders, "Duplicate outgoing order: " + eid)
        edges[eid] = edge
        pairs[source, target] = edge
        orders.add((source, edge["order"]))
    paths = {}
    for path in array(graph["main_paths"], "main_paths"):
        fields(path, {"path_id", "case_ids"}, "main path")
        pid = text_value(path["path_id"], "path_id")
        require(pid not in paths, "Duplicate path_id: " + pid)
        ids = string_array(path["case_ids"], "main path.case_ids", unique=True)
        require(len(ids) >= 2, "Main path requires at least two cases: " + pid)
        require(set(ids) <= set(store), "Main path references an unknown case ID: " + pid)
        for pair in zip(ids, ids[1:]):
            require(pair in pairs and pairs[pair]["relation_type"] == "next", "Main path is missing a next edge: " + pid)
        paths[pid] = path
    sequences = list(paths.items())
    for i, (pid, path) in enumerate(sequences):
        smaller = path["case_ids"]
        for j, (_, other) in enumerate(sequences):
            if i == j:
                continue
            larger = other["case_ids"]
            if len(smaller) <= len(larger):
                require(not any(larger[k:k + len(smaller)] == smaller
                                for k in range(len(larger) - len(smaller) + 1)),
                        "Duplicate or redundant contiguous main path: " + pid)
    return edges, paths


def identity(edge):
    return edge["from_case_id"], edge["to_case_id"], edge["relation_type"]


def boundary_ids(old_ids, new_ids):
    if not new_ids:
        return {old_ids[0], old_ids[-1]}
    old_pairs = set(zip(old_ids, old_ids[1:]))
    new_pairs = set(zip(new_ids, new_ids[1:]))
    return {cid for pair in old_pairs ^ new_pairs for cid in pair}


def review_index(review, store):
    if review is None:
        review = {"edge_changes": [], "path_changes": []}
    fields(review, {"edge_changes", "path_changes"}, "local change review")
    result = {}
    for group, id_key in (("edge_changes", "edge_id"), ("path_changes", "path_id")):
        indexed = {}
        for item in array(review[group], group):
            fields(item, {id_key, "reason", "checked_case_ids"}, group + " item")
            item_id = text_value(item[id_key], id_key)
            text_value(item["reason"], "change reason")
            checked = string_array(item["checked_case_ids"], "checked_case_ids", nonempty=True, unique=True)
            require(set(checked) <= set(store), "Change review contains unknown case IDs")
            require(item_id not in indexed, "Duplicate change review ID: " + item_id)
            indexed[item_id] = item
        result[group] = indexed
    return result


def validate_incremental(existing, graph, store, review=None):
    old_edges, old_paths = graph_index(existing, store)
    new_edges, new_paths = graph_index(graph, store)
    reviews = review_index(review, store)
    removed = set(old_edges) - set(new_edges)
    changed_paths = {pid for pid, path in old_paths.items()
                     if pid not in new_paths or path["case_ids"] != new_paths[pid]["case_ids"]}
    require(set(reviews["edge_changes"]) == removed,
            "Removed historical edges require an exact local edge_changes review; stale reviews are invalid")
    require(set(reviews["path_changes"]) == changed_paths,
            "Changed/removed historical main paths require an exact local path_changes review")
    for eid in set(old_edges) & set(new_edges):
        require(identity(old_edges[eid]) == identity(new_edges[eid]),
                "Historical edge ID cannot be reused for changed endpoints or type: " + eid)
    # Semantically unchanged edges/paths may not be silently assigned fresh IDs.
    new_by_identity = {identity(edge): eid for eid, edge in new_edges.items()}
    new_by_sequence = {tuple(path["case_ids"]): pid for pid, path in new_paths.items()}
    for eid, edge in old_edges.items():
        if identity(edge) in new_by_identity:
            require(new_by_identity[identity(edge)] == eid, "Preserve unchanged historical edge_id: " + eid)
    for pid, path in old_paths.items():
        seq = tuple(path["case_ids"])
        if seq in new_by_sequence:
            require(new_by_sequence[seq] == pid, "Preserve unchanged historical path_id: " + pid)
    for eid in removed:
        require(set(identity(old_edges[eid])[:2]) <= set(reviews["edge_changes"][eid]["checked_case_ids"]),
                "Removed edge review must include both endpoint cases: " + eid)
    for pid in changed_paths:
        new_ids = new_paths[pid]["case_ids"] if pid in new_paths else []
        needed = boundary_ids(old_paths[pid]["case_ids"], new_ids)
        require(needed <= set(reviews["path_changes"][pid]["checked_case_ids"]),
                "Main path review must include changed boundaries: " + pid)
    return {"edge_count": len(new_edges), "main_path_count": len(new_paths),
            "added_edge_count": len(set(new_edges) - set(old_edges)),
            "removed_edge_count": len(removed), "changed_main_path_count": len(changed_paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="The four-field skill request JSON")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-input", action="store_true")
    mode.add_argument("--graph", help="Candidate cumulative graph JSON")
    parser.add_argument("--changes", help="Local semantic change review, never part of public graph")
    args = parser.parse_args()
    try:
        require(not (args.check_input and args.changes), "--changes requires --graph")
        request, store = load_request(args.input)
        graph_index(request["existing_graph"], store)
        if args.check_input:
            count = len(current_case_ids(request))
            summary = {"valid": True, "batch_case_count": count, "total_case_count": len(store)}
            if count > RECOMMENDED_BATCH_SIZE:
                summary["advisories"] = ["本轮去重用例 ID 超过建议的 30 个；请结合正文、需求和历史图谱大小评估拆批。单次查询仍最多 10 条。"]
            emit(summary)
        else:
            graph = read_json(args.graph)
            review = read_json(args.changes) if args.changes else None
            counts = validate_incremental(request["existing_graph"], graph, store, review)
            emit({"valid": True, **counts})
        return 0
    except ContractError as exc:
        emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
