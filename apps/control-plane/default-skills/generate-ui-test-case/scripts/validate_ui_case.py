#!/usr/bin/env python3
"""Validate generate-ui-test-case YAML output."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml


VALID_KEYWORDS = {
    "open",
    "reload",
    "click",
    "dblclick",
    "input",
    "clear",
    "press",
    "wait_text",
    "assert_text",
    "assert_visible",
    "assert_hidden",
    "assert_url",
    "screenshot",
    "sleep",
}
VALID_LOCATOR_TYPES = {
    "css",
    "xpath",
    "text",
    "placeholder",
    "label",
    "test_id",
    "testid",
    "role",
}
LOCATOR_REQUIRED = {
    "click",
    "dblclick",
    "input",
    "clear",
    "press",
    "wait_text",
    "assert_text",
    "assert_visible",
    "assert_hidden",
}
LOCATOR_FORBIDDEN = {"open", "reload", "assert_url", "screenshot", "sleep"}
OPERATION_REQUIRED = {
    "open",
    "input",
    "press",
    "wait_text",
    "assert_text",
    "assert_visible",
    "assert_hidden",
    "assert_url",
    "sleep",
}
OPERATION_FORBIDDEN = {"clear", "screenshot"}
COMPARATOR_REQUIRED = {"assert_text", "assert_url"}
VALID_COMPARATORS = {"eq", "contains"}
WRITE_KEYWORDS = {"click", "dblclick", "input", "clear", "press"}
ASSERT_KEYWORDS = {
    "wait_text",
    "assert_text",
    "assert_visible",
    "assert_hidden",
    "assert_url",
}

CLASS_SUBSTRING_RE = re.compile(r"contains\s*\(\s*@class\s*,", re.IGNORECASE)
POSITIONAL_RE = re.compile(r":nth-(?:child|of-type)\b", re.IGNORECASE)
EXACT_LABEL_RE = re.compile(
    r"//label\s*\[\s*(?:normalize-space\s*\(\s*\.\s*\)|text\s*\(\s*\)|\.)\s*=\s*['\"]",
    re.IGNORECASE,
)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def validate_url(
    value: str, base_url: str, allow_localhost: bool, case_name: str, index: int
) -> None:
    from ui_variable_template import parse_tokens
    try:
        parse_tokens(value)
    except ValueError as exc:
        fail(str(exc))
    # The environment supplies baseUrl at execution; validate its path without guessing a host.
    if value.startswith("{{baseUrl}}") and (len(value) == 11 or value[11:].startswith("/")):
        value = (base_url or "https://environment.invalid") + value[11:]
    for token in reversed(parse_tokens(value)):
        value = value[:token.start] + "variable" + value[token.end:]
    parsed = urlparse(value)
    require(
        parsed.scheme in {"http", "https"},
        f"{case_name}: step {index} open URL must use http or https",
    )
    require(
        bool(parsed.hostname), f"{case_name}: step {index} open URL must include a host"
    )
    if not allow_localhost:
        require(
            (parsed.hostname or "").lower() not in LOCAL_HOSTS,
            f"{case_name}: step {index} open URL must not use localhost/127.0.0.1; pass --allow-localhost only for a local target",
        )
    if base_url:
        base = urlparse(base_url)
        require(
            base.scheme in {"http", "https"} and bool(base.hostname),
            "--base-url must be an absolute http(s) URL",
        )
        require(
            parsed.scheme == base.scheme and parsed.netloc == base.netloc,
            f"{case_name}: step {index} open URL {value!r} must use targetBaseUrl {base_url!r}",
        )
        base_path = base.path.rstrip("/")
        require(
            parsed.path == base_path or parsed.path.startswith(base_path + "/"),
            f"{case_name}: step {index} open URL {value!r} must stay under targetBaseUrl path {base_path or '/'}",
        )


def validate_xpath_delimiters(value: str, context: str) -> None:
    """Check lexical balance, not the full XPath grammar or DOM semantics."""
    from ui_variable_template import parse_tokens

    try:
        tokens = parse_tokens(value)
    except ValueError as exc:
        fail(f"{context}: {exc}")
    for token in reversed(tokens):
        value = value[:token.start] + "variable" + value[token.end:]
    stack = []
    quote = None
    for offset, char in enumerate(value):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "([":
            stack.append(char)
        elif char in ")]":
            expected = "(" if char == ")" else "["
            require(bool(stack) and stack[-1] == expected,
                    f"{context}: XPath mismatched delimiter {char!r} at offset {offset}")
            stack.pop()
    require(quote is None, f"{context}: XPath has an unclosed string literal")
    require(not stack, f"{context}: XPath has unclosed delimiters {''.join(stack)!r}")


def validate_locator(
    step: dict, case_name: str, index: int, evidenced_locators=None
) -> None:
    locator_type = step.get("locatorType")
    locator_value = str(step.get("locatorValue") or "")
    if locator_type == "xpath":
        validate_xpath_delimiters(locator_value, f"{case_name}: step {index}")
    if evidenced_locators is False:
        return  # Human-authored locators need no repeat AI evidence review.
    if evidenced_locators and (locator_type, locator_value) in evidenced_locators:
        return
    if locator_type in {"css", "xpath"}:
        require(
            not CLASS_SUBSTRING_RE.search(locator_value),
            f"{case_name}: step {index} locator must not use contains(@class, ...); it matches class fragments and breaks strict mode",
        )
        # Prefixes do not establish or refute rendered DOM correctness. Check
        # dependency version, render branch and uniqueness in the semantic audit.
        require(
            not POSITIONAL_RE.search(locator_value),
            f"{case_name}: step {index} locator must not use :nth-child/:nth-of-type; scope the row or control semantically",
        )
        require(
            not EXACT_LABEL_RE.search(locator_value),
            f"{case_name}: step {index} locator must not use exact equality on a whole form label; required labels can append a marker such as '*'. Use //label[.//span[normalize-space(.)='字段名']]/following::input[1] or contains(normalize-space(.),'字段名')",
        )


def validate_step(
    step: object,
    index: int,
    case_name: str,
    base_url: str,
    allow_localhost: bool,
    evidenced_locators=None,
    allow_missing=False,
) -> None:
    require(isinstance(step, dict), f"{case_name}: step {index} must be an object")
    from missing_fields import validate_missing

    try:
        pending = validate_missing(step)
    except ValueError as exc:
        fail(f"{case_name}: step {index}: {exc}")
    require(
        allow_missing or not step.get("missingFields"),
        f"{case_name}: step {index} has unresolved missingFields",
    )
    from ui_step_extract import normalize_save_to
    from ui_variable_template import validate_step_variables
    try:
        validate_step_variables(step)
        normalize_save_to(step, field_path=f"{case_name}.steps[{index}]")
    except ValueError as exc:
        fail(str(exc))
    original = step
    step = dict(step)
    step.pop("missingFields", None)
    step.pop("saveTo", None)
    # Validate all supplied fields, substituting only explicitly declared nulls.
    samples = {
        "keyword": "click",
        "locatorType": "css",
        "locatorValue": "[data-pending]",
        "operationValue": "pending",
        "comparator": "eq",
    }
    if original.get("keyword") in {"assert_visible", "assert_hidden", "sleep"}:
        samples["operationValue"] = "10000"
    if original.get("keyword") == "open":
        samples["operationValue"] = base_url or "https://pending.invalid/"
    for field in pending:
        step[field] = samples[field]
    if "keyword" in pending:
        # Unknown lowering cannot claim a runnable operation. Supplied types still checked.
        require(allow_missing, f"{case_name}: unresolved keyword")
        allowed = {
            "orderNo",
            "stepName",
            "keyword",
            "continueOnFailure",
            "enabled",
            "locatorType",
            "locatorValue",
            "operationValue",
            "comparator",
        }
        require(not set(step) - allowed, f"{case_name}: unsupported step field")
        require(
            type(step.get("orderNo")) is int and step["orderNo"] == index,
            "invalid step order",
        )
        require(
            isinstance(step.get("stepName"), str) and bool(step["stepName"].strip()),
            "missing stepName",
        )
        require(
            type(step.get("enabled")) is bool
            and type(step.get("continueOnFailure")) is bool,
            "invalid flags",
        )
        for field in ("locatorType", "locatorValue", "operationValue", "comparator"):
            if field in step:
                require(
                    isinstance(step[field], str) and bool(step[field]),
                    f"{field} must be a string or declared missing",
                )
        return

    for key in ("orderNo", "stepName", "keyword", "continueOnFailure", "enabled"):
        require(key in step, f"{case_name}: step {index} missing {key}")
    require(
        not set(step)
        - {
            "orderNo",
            "stepName",
            "keyword",
            "continueOnFailure",
            "enabled",
            "locatorType",
            "locatorValue",
            "operationValue",
            "comparator",
        },
        f"{case_name}: step {index} has unsupported fields",
    )

    require(
        type(step["orderNo"]) is int,
        f"{case_name}: step {index} orderNo must be integer",
    )
    require(
        step["orderNo"] == index,
        f"{case_name}: step orderNo must start at 1 and increment by 1",
    )
    require(
        isinstance(step["stepName"], str) and step["stepName"],
        f"{case_name}: step {index} stepName must be non-empty",
    )
    require(
        isinstance(step["keyword"], str) and step["keyword"],
        f"{case_name}: step {index} keyword must be non-empty",
    )
    require(
        isinstance(step["continueOnFailure"], bool),
        f"{case_name}: step {index} continueOnFailure must be boolean",
    )
    require(
        isinstance(step["enabled"], bool),
        f"{case_name}: step {index} enabled must be boolean",
    )

    keyword = step["keyword"]
    require(
        keyword in VALID_KEYWORDS,
        f"{case_name}: step {index} keyword {keyword} is not supported",
    )

    if keyword in LOCATOR_REQUIRED:
        require(
            "locatorType" in step,
            f"{case_name}: step {index} keyword {keyword} requires locatorType",
        )
        require(
            "locatorValue" in step,
            f"{case_name}: step {index} keyword {keyword} requires locatorValue",
        )
        require(
            isinstance(step["locatorType"], str) and step["locatorType"],
            f"{case_name}: step {index} locatorType must be non-empty",
        )
        require(
            isinstance(step["locatorValue"], str) and step["locatorValue"],
            f"{case_name}: step {index} locatorValue must be non-empty",
        )
        require(
            step["locatorType"] in VALID_LOCATOR_TYPES,
            f"{case_name}: step {index} locatorType {step['locatorType']} is not supported",
        )
        validate_locator(step, case_name, index, evidenced_locators)

    if keyword in LOCATOR_FORBIDDEN:
        require(
            "locatorType" not in step,
            f"{case_name}: step {index} keyword {keyword} should not include locatorType",
        )
        require(
            "locatorValue" not in step,
            f"{case_name}: step {index} keyword {keyword} should not include locatorValue",
        )

    if keyword in OPERATION_REQUIRED:
        require(
            "operationValue" in step,
            f"{case_name}: step {index} keyword {keyword} requires operationValue",
        )
        require(
            step["operationValue"] is not None and str(step["operationValue"]) != "",
            f"{case_name}: step {index} operationValue must be non-empty",
        )

    if keyword in OPERATION_FORBIDDEN:
        require(
            "operationValue" not in step,
            f"{case_name}: step {index} keyword {keyword} should not include operationValue",
        )

    if keyword == "open":
        validate_url(
            str(step["operationValue"]), base_url, allow_localhost, case_name, index
        )
    if keyword in OPERATION_REQUIRED and keyword not in {
        "assert_visible",
        "assert_hidden",
        "sleep",
    }:
        require(
            isinstance(step["operationValue"], str),
            f"{case_name}: step {index} operationValue must be a string",
        )
    if keyword in {"assert_visible", "assert_hidden", "sleep"}:
        value = step["operationValue"]
        require(
            type(value) is int or isinstance(value, str) and value.isdigit(),
            f"{case_name}: step {index} requires integer milliseconds",
        )
        require(
            int(value) > 0
            if keyword in {"assert_visible", "assert_hidden"}
            else int(value) >= 0,
            f"{case_name}: step {index} invalid milliseconds",
        )

    if keyword in COMPARATOR_REQUIRED:
        require(
            "comparator" in step,
            f"{case_name}: step {index} keyword {keyword} requires comparator",
        )
        require(
            step["comparator"] in VALID_COMPARATORS,
            f"{case_name}: step {index} comparator must be eq or contains",
        )
    else:
        require(
            "comparator" not in step,
            f"{case_name}: step {index} keyword {keyword} should not include comparator",
        )


def validate_case(
    case: object,
    index: int,
    base_url: str,
    allow_localhost: bool,
    evidenced_locators=None,
    allow_missing=False,
) -> None:
    require(isinstance(case, dict), f"case {index} must be an object")
    for key in ("name", "enabled", "stepsJson", "orderNo"):
        require(key in case, f"case {index} missing {key}")
    require(
        not set(case) - {"name", "enabled", "stepsJson", "orderNo"},
        f"case {index} has unsupported fields",
    )

    case_name = str(case["name"])
    require(
        isinstance(case["name"], str) and case["name"],
        f"case {index} name must be non-empty",
    )
    require(isinstance(case["enabled"], bool), f"{case_name}: enabled must be boolean")
    require(
        isinstance(case["stepsJson"], list) and bool(case["stepsJson"]),
        f"{case_name}: stepsJson must be a non-empty array",
    )
    require(type(case["orderNo"]) is int, f"{case_name}: orderNo must be integer")
    require(case["orderNo"] == index, "case orderNo must start at 1 and increment by 1")

    for step_index, step in enumerate(case["stepsJson"], start=1):
        if isinstance(step, dict):
            require(not any("{{data." in str(step.get(key, "")) for key in ("locatorValue", "operationValue")),
                    f"{case_name}: step {step_index} must use original fields, not data bindings")
        validate_step(
            step,
            step_index,
            case_name,
            base_url,
            allow_localhost,
            evidenced_locators,
            allow_missing,
        )

    last_write = max(
        (
            i
            for i, step in enumerate(case["stepsJson"])
            if step.get("keyword") in WRITE_KEYWORDS
        ),
        default=-1,
    )
    if last_write >= 0 and not (
        allow_missing and any(s.get("missingFields") for s in case["stepsJson"])
    ):
        require(
            any(
                step.get("keyword") in ASSERT_KEYWORDS
                for step in case["stepsJson"][last_write + 1 :]
            ),
            f"{case_name}: case has write actions but no assertion after the last write; a toast or screenshot alone is not enough",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate generate-ui-test-case YAML output"
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Validate an editable draft, not execution readiness",
    )
    parser.add_argument("path", type=Path, help="YAML file to validate")
    parser.add_argument("--design", type=Path, help="Reviewed design JSON for case name/order checks")
    parser.add_argument(
        "--base-url",
        default="",
        help="Required target origin, e.g. http://10.9.103.80:30080",
    )
    parser.add_argument(
        "--bundle", type=Path, help="Frozen stage-one/two inputs and execution context"
    )
    parser.add_argument(
        "--trace", type=Path, help="Internal trace sidecar, never part of the YAML"
    )
    parser.add_argument(
        "--repair",
        type=Path,
        help="Evidence-backed completion proposal for non-ready input",
    )
    parser.add_argument(
        "--allow-localhost",
        action="store_true",
        help="Allow localhost/127.0.0.1 open URLs (only for a local target)",
    )
    args = parser.parse_args()

    data = yaml.safe_load(args.path.read_text(encoding="utf-8"))
    cases = data if isinstance(data, list) else [data]
    require(
        isinstance(cases, list) and (bool(cases) or args.allow_missing),
        "output must contain at least one case",
    )

    evidence = False
    if args.bundle:
        from handoff import (
            effective_bundle,
            preflight,
            evidenced_locators,
            validate_handoff,
            HandoffError,
        )

        try:
            bundle = effective_bundle(
                json.loads(args.bundle.read_text()),
                json.loads(args.repair.read_text()) if args.repair else None,
            )
            preflight(bundle)
            require(args.trace is not None, "--bundle requires --trace")
            require(isinstance(data, list), "scenario handoff requires a YAML list")
            require(
                not args.base_url
                or args.base_url == bundle["context"]["targetBaseUrl"],
                "--base-url differs from the frozen context",
            )
            args.base_url = bundle["context"]["targetBaseUrl"]
            validate_handoff(cases, bundle, json.loads(args.trace.read_text()))
            evidence = evidenced_locators(bundle)
        except HandoffError as exc:
            fail(str(exc))
    else:
        require(not args.trace and not args.repair, "--trace/--repair require --bundle")
    for index, case in enumerate(cases, start=1):
        validate_case(
            case,
            index,
            args.base_url,
            args.allow_localhost,
            evidence,
            args.allow_missing,
        )

    if args.design:
        designs = json.loads(args.design.read_text())["cases"]
        retained = [case for case in designs if case["coverage"] != "excluded"]
        require([c["name"] for c in cases] == [c["name"] for c in retained], "case names/order differ from reviewed design")

    missing = sum(
        len(s.get("missingFields", [])) for c in cases for s in c["stepsJson"]
    )
    print(
        f"OK: validated {len(cases)} UI test case(s); unresolved entries={missing}; mode={'draft' if args.allow_missing else 'complete'}"
    )


if __name__ == "__main__":
    main()
