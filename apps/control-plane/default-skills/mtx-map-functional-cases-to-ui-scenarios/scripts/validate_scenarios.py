"""Validate UI designs independently of element/fixture availability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from jsonschema import Draft202012Validator

from validate_legacy_scenarios import normalize

from execution_profile import load_profile

DEFAULT_CAPABILITIES = load_profile()["capabilities"]

def validate(report, *, cases, surface=None, requirements=None, capabilities=None, execution_profile=None):
    if isinstance(report, dict) and report.get("schemaVersion") == "ui_test_scenarios/1.0":
        from validate_legacy_scenarios import validate as legacy

        return legacy(
            report,
            cases=cases,
            surface=surface or {},
            requirements=requirements,
            capabilities=capabilities,
        )
    schema = json.loads((Path(__file__).resolve().parent.parent / 'references/output.schema.json').read_text())
    errors = [f'{e.json_path}: {e.message}' for e in Draft202012Validator(schema).iter_errors(report)]
    if errors:
        return errors

    def check(ok, message):
        if not ok:
            errors.append(message)

    check(
        report.get("schemaVersion") == "ui_test_scenarios/2.0",
        "unsupported schemaVersion",
    )
    source = cases.get("cases") if isinstance(cases, dict) else cases
    if not isinstance(source, list) or any(not isinstance(c, dict) or not isinstance(c.get('caseId'), str)
            or not c['caseId'].strip() for c in source):
        return ['source cases must contain nonempty caseId strings']
    if len({c['caseId'] for c in source}) != len(source):
        return ['duplicate source caseId']
    for c in source:
        content = c.get('content', {})
        if (not isinstance(c.get('title'), str) or not isinstance(content, dict)
                or not isinstance(content.get('steps'), list)
                or not isinstance(content.get('preconditions', []), list)
                or any(not isinstance(x, str) for x in content.get('preconditions', []))
                or any(not isinstance(step, dict) or not isinstance(step.get('action'), str)
                       or not isinstance(step.get('expected'), str) for step in content.get('steps', []))):
            return [f"{c['caseId']}: incomplete source title/content/steps"]
    originals = {c["caseId"]: c for c in source}
    profile = report.get("capabilities", {})
    for name in ("operations", "assertions"):
        check(
            isinstance(profile.get(name), list)
            and all(isinstance(v, str) for v in profile.get(name, [])),
            f"missing capabilities.{name}",
        )
    runtime_profile = load_profile(execution_profile) if execution_profile else load_profile()
    if execution_profile and capabilities is not None:
        check(capabilities == runtime_profile['capabilities'], 'caller capabilities conflict with execution profile')
    expected_profile = capabilities if capabilities is not None else runtime_profile['capabilities']
    check(
        profile == expected_profile, "capabilities differ from caller/platform profile"
    )
    designs = report.get("cases", [])
    check(isinstance(designs, list), "cases must be an array")
    if not isinstance(designs, list):
        return errors
    seen = set()
    forbidden = {
        "actionBindings",
        "observationBindings",
        "locatorType",
        "locatorValue",
        "dataPlan",
    }
    for case in designs:
        cid = case.get("caseId")
        check(cid in originals and cid not in seen, f"{cid}: unknown/duplicate case")
        seen.add(cid)
        if cid not in originals:
            continue
        original = originals[cid]
        check(
            case.get("sourceTitle") == original["title"], f"{cid}: source title changed"
        )
        check(
            bool(case.get("name")) and bool(case.get("goal")),
            f"{cid}: name/goal required",
        )
        check(
            case.get("preconditions") == original["content"].get("preconditions", []),
            f"{cid}: original preconditions changed",
        )
        check(
            not forbidden.intersection(case),
            f"{cid}: design contains execution bindings",
        )
        steps = case.get("steps", [])
        check(
            len(steps) == len(original["content"]["steps"]),
            f"{cid}: source steps missing/extra",
        )
        ids = set()
        action_ids = set()
        statuses = []
        excluded_ids = set()
        excluded_actions = False
        for index, (step, src) in enumerate(
            zip(steps, original["content"]["steps"]), 1
        ):
            path = f"{cid} step {index}"
            check(
                step.get("sourceStepNo") == index
                and step.get("sourceAction") == src["action"],
                f"{path}: source action/order changed",
            )
            check(
                not forbidden.intersection(step),
                f"{path}: locator binding belongs to stage three",
            )
            action_text = normalize(src["action"])
            action_occupied = [False] * len(action_text)
            for action in step.get("actions", []):
                aid = action.get("actionId")
                check(
                    bool(aid) and aid not in action_ids,
                    f"{path}: missing/duplicate actionId",
                )
                action_ids.add(aid)
                check(
                    not forbidden.intersection(action),
                    f"{path}: locator binding belongs to stage three",
                )
                check(
                    bool(action.get("action"))
                    and isinstance(action.get("target"), str)
                    and "value" in action,
                    f"{path}: action/target/value required",
                )
                state = action.get("status")
                op = action.get("operation")
                check(
                    state in ("included", "excluded"), f"{path}: invalid action status"
                )
                statuses.append(state)
                if state == "included":
                    check(
                        op in profile.get("operations", []),
                        f"{path}: unsupported included operation {op}",
                    )
                else:
                    excluded_actions = True
                    check(
                        op not in profile.get("operations", [])
                        and bool(action.get("reason")),
                        f"{path}: exclusion needs unsupported capability and reason",
                    )
                quote = action.get("sourceQuote", "")
                check(
                    bool(quote) and quote in src["action"],
                    f"{path}/{aid}: source action excerpt changed",
                )
                part = normalize(quote)
                offset = action_text.find(part) if part else -1
                while offset >= 0 and any(action_occupied[offset : offset + len(part)]):
                    offset = action_text.find(part, offset + 1)
                if offset < 0:
                    check(False, f"{path}/{aid}: overlapping action excerpt")
                else:
                    action_occupied[offset : offset + len(part)] = [True] * len(part)
            check(all(action_occupied), f"{path}: unaccounted source action")
            occupied = [False] * len(normalize(src["expected"]))
            for exp in step.get("expectations", []):
                eid = exp.get("expectationId")
                status = exp.get("status")
                assertion = exp.get("assertion")
                check(
                    bool(eid) and eid not in ids,
                    f"{path}: missing/duplicate expectation ID",
                )
                ids.add(eid)
                check(
                    status in ("included", "excluded", "bookkeeping"),
                    f"{path}/{eid}: invalid status",
                )
                check(
                    "value" in exp and isinstance(exp.get("target"), str),
                    f"{path}/{eid}: target/value required",
                )
                if status != "bookkeeping":
                    statuses.append(status)
                if status == "included":
                    check(
                        assertion in profile.get("assertions", []),
                        f"{path}/{eid}: unsupported assertion {assertion}",
                    )
                elif status == "excluded":
                    excluded_ids.add(eid)
                    check(
                        assertion not in profile.get("assertions", [])
                        and bool(exp.get("reason")),
                        f"{path}/{eid}: exclusion needs unsupported capability and reason",
                    )
                else:
                    check(
                        assertion == "record" and bool(exp.get("reason")),
                        f"{path}/{eid}: bookkeeping requires recording reason",
                    )
                quote = exp.get("sourceQuote", "")
                check(
                    bool(quote) and quote in src["expected"],
                    f"{path}/{eid}: source excerpt changed",
                )
                text = normalize(src["expected"])
                part = normalize(quote)
                offset = text.find(part) if part else -1
                while offset >= 0 and any(occupied[offset : offset + len(part)]):
                    offset = text.find(part, offset + 1)
                if offset < 0:
                    check(False, f"{path}/{eid}: overlapping/invalid excerpt")
                else:
                    occupied[offset : offset + len(part)] = [True] * len(part)
            check(all(occupied), f"{path}: unaccounted expected text")
        check(not action_ids.intersection(ids), f'{cid}: actionId and expectationId must share one unique namespace')
        core = case.get("coreExpectationIds", [])
        check(bool(core) and set(core) <= ids, f"{cid}: unresolved core expectations")
        coverage = (
            "full"
            if statuses and all(s == "included" for s in statuses)
            else "partial"
            if "included" in statuses
            else "excluded"
        )
        check(case.get("coverage") == coverage, f"{cid}: coverage must be {coverage}")
        check(
            isinstance(case.get("limitations"), list),
            f"{cid}: limitations must be an array",
        )
        if set(core) & excluded_ids or excluded_actions:
            check(
                bool(case.get("limitations")),
                f"{cid}: excluded core/action needs limitations",
            )
    check(seen == set(originals), "selected source cases missing from design")
    check([c['caseId'] for c in designs] == [c['caseId'] for c in source], 'case order differs from supplied source')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--surface", type=Path)
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--capabilities", type=Path)
    parser.add_argument("--execution-profile", type=Path)
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Legacy v1 normalization only; v2 designs are never stripped",
    )
    args = parser.parse_args()
    report = json.loads(args.artifact.read_text())

    def read(path):
        return json.loads(path.read_text()) if path else None

    if args.finalize and report.get("schemaVersion") == "ui_test_scenarios/1.0":
        from validate_legacy_scenarios import normalize_handoff

        report, _ = normalize_handoff(report, read(args.surface))
    errors = validate(
        report,
        cases=read(args.cases),
        surface=read(args.surface),
        requirements=read(args.requirements),
        capabilities=read(args.capabilities),
        execution_profile=args.execution_profile,
    )
    if errors:
        raise SystemExit("\n".join(errors))
    if args.finalize:
        args.artifact.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
    print(
        "OK: source actions, prerequisites, expected clauses, capability exclusions and design coverage"
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(f"Scenario validation failed: {error}")
