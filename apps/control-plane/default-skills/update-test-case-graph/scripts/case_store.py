"""Shared read-only JSON/input validation. Uses Python standard library only."""
import json
from pathlib import Path


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def text_value(value, where, nonempty=True):
    require(isinstance(value, str), where + " must be a string")
    if nonempty:
        require(bool(value.strip()), where + " must be nonempty")
    return value  # Never normalize an ID or source text.


def fields(value, expected, where):
    require(isinstance(value, dict), where + " must be an object")
    require(set(value) == set(expected), where + " has missing or extra fields")


def array(value, where):
    require(isinstance(value, list), where + " must be an array")
    return value


def string_array(value, where, nonempty=False, unique=False):
    array(value, where)
    if nonempty:
        require(bool(value), where + " must not be empty")
    for item in value:
        text_value(item, where + "[]")
    if unique:
        require(len(set(value)) == len(value), where + " contains duplicates")
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON contains a duplicate object key")
        result[key] = value
    return result


def _constant(value):
    raise ContractError("JSON contains a non-finite number")


def read_json(path):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_object, parse_constant=_constant)
    except (OSError, UnicodeError) as exc:
        raise ContractError("Cannot read JSON file: " + str(path)) from exc
    except json.JSONDecodeError as exc:
        raise ContractError("Invalid JSON at line %d, column %d" % (exc.lineno, exc.colno)) from exc


def case_index(cases, where="cases"):
    array(cases, where)
    result = {}
    required = {"case_id", "case_module", "case_title", "case_type", "priority",
                "precondition", "test_steps", "expected_results"}
    for i, case in enumerate(cases):
        loc = "%s[%d]" % (where, i)
        require(isinstance(case, dict) and required <= set(case), loc + " lacks complete case fields")
        for key in ("case_id", "case_title", "case_module", "case_type", "priority"):
            text_value(case[key], loc + "." + key, key in ("case_id", "case_title"))
        for key in ("precondition", "test_steps", "expected_results"):
            string_array(case[key], loc + "." + key, nonempty=key != "precondition")
        require(len(case["test_steps"]) == len(case["expected_results"]), loc + " step/result counts differ")
        cid = case["case_id"]
        require(cid not in result, loc + " duplicates case_id")
        result[cid] = case
    return result


def load_store(path):
    require(Path(path).is_absolute(), "case_file_path must be absolute")
    value = read_json(path)
    fields(value, {"cases"}, "case file")
    return case_index(value["cases"], "case file.cases")


def current_case_ids(request):
    """Return current batch IDs in first-seen order; call after load_request validation."""
    return list(dict.fromkeys(cid for link in request["case_requirement_links"] for cid in link["case_ids"]))


def load_request(path):
    value = read_json(path)
    fields(value, {"requirements", "case_requirement_links", "case_file_path", "existing_graph"}, "input")
    text_value(value["case_file_path"], "case_file_path")
    store = load_store(value["case_file_path"])
    reqs = set()
    for req in array(value["requirements"], "requirements"):
        fields(req, {"requirement_id", "requirement_title", "requirement_content"}, "requirement")
        for key in req:
            text_value(req[key], "requirement." + key)
        require(req["requirement_id"] not in reqs, "Duplicate requirement_id")
        reqs.add(req["requirement_id"])
    mapped = set()
    bound, unbound = set(), set()
    for link in array(value["case_requirement_links"], "case_requirement_links"):
        fields(link, {"requirement_id", "case_ids"}, "requirement link")
        rid = link["requirement_id"]
        if rid is not None:
            text_value(rid, "link.requirement_id")
            require(rid in reqs, "Mapping references an unknown requirement_id")
        require(rid not in mapped, "Duplicate requirement mapping")
        mapped.add(rid)
        ids = string_array(link["case_ids"], "link.case_ids", nonempty=True, unique=True)
        require(set(ids) <= set(store), "Mapping references a case ID absent from case file")
        (unbound if rid is None else bound).update(ids)
    require(not (bound & unbound), "A case cannot be both requirement-bound and unbound in one batch")
    return value, store


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
