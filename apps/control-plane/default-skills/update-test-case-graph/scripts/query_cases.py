#!/usr/bin/env python3
"""Fetch at most ten complete cases, or search at most ten compact candidates."""
import argparse
import json
import sys
from case_store import ContractError, emit, load_store, require, string_array, text_value

MAX_CASES = 10


def get_cases(store, case_ids):
    string_array(case_ids, "case_ids", nonempty=True, unique=True)
    require(len(case_ids) <= MAX_CASES, "A query may request at most 10 case IDs")
    found = [store[cid] for cid in case_ids if cid in store]
    missing = [cid for cid in case_ids if cid not in store]
    return {"cases": found, "not_found_case_ids": missing}


def search_cases(store, query="", module=None, limit=10):
    require(type(limit) is int and 1 <= limit <= MAX_CASES, "Search limit must be an integer from 1 to 10")
    text_value(query, "query", nonempty=False)
    if module is not None:
        text_value(module, "module")
    require(bool(query.strip()) or module is not None, "Search requires specific keywords or an exact module")
    terms = query.casefold().split()
    require(not any(term in ("*", "%", ".*") for term in terms), "Wildcard listing is not supported")
    matches = []
    for case in store.values():
        if module is not None and case["case_module"] != module:
            continue
        title = case["case_title"].casefold()
        brief = (case["case_module"] + " " + case["case_title"]).casefold()
        content = " ".join([brief] + case["precondition"] + case["test_steps"] + case["expected_results"]).casefold()
        if all(term in content for term in terms):
            score = sum(3 * (term in title) + (term in brief) for term in terms)
            matches.append((score, case))
    matches.sort(key=lambda pair: (-pair[0], pair[1]["case_id"]))
    return {
        "matches": [{key: case[key] for key in ("case_id", "case_module", "case_title")}
                    for _, case in matches[:limit]],
        "has_more": len(matches) > limit,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    get = sub.add_parser("get", help="Return 1-10 complete cases, with explicit missing IDs")
    get.add_argument("--case-file", required=True)
    get.add_argument("--case-ids", required=True, help='JSON array, e.g. ["C01","C02"]')
    search = sub.add_parser("search", help="Return compact relevant candidates; no list-all or pagination")
    search.add_argument("--case-file", required=True)
    search.add_argument("--query", default="")
    search.add_argument("--module")
    search.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    try:
        # Fail oversized/invalid requests before reading the source file.
        if args.command == "get":
            try:
                args.case_ids = json.loads(args.case_ids)
            except json.JSONDecodeError as exc:
                raise ContractError("--case-ids must be a JSON array of original IDs") from exc
            get_cases({}, args.case_ids)
        else:
            search_cases({}, args.query, args.module, args.limit)
        store = load_store(args.case_file)
        if args.command == "get":
            result = get_cases(store, args.case_ids)
            emit(result)
            return 3 if result["not_found_case_ids"] else 0
        emit(search_cases(store, args.query, args.module, args.limit))
        return 0
    except ContractError as exc:
        emit({"error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
