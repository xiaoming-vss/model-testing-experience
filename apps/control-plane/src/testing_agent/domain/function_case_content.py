"""Canonical functional case body, plus conservative legacy text conversion."""

import re

from pydantic import BaseModel, ConfigDict


class CaseStep(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    action: str
    expected: str


class CaseContent(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    preconditions: list[str]
    steps: list[CaseStep]


def numbered_parts(value: str):
    matches = list(re.finditer(r"(?m)^\s*(\d+)[.、．)）]\s*", value))
    if not matches or value[: matches[0].start()].strip():
        return None
    if [int(m.group(1)) for m in matches] != list(range(1, len(matches) + 1)):
        return None
    return [
        value[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(value)].strip()
        for i, m in enumerate(matches)
    ]


def from_legacy(preconditions="", steps="", expected_results=""):
    preconditions, steps, expected_results = (
        str(v or "") for v in (preconditions, steps, expected_results)
    )
    actions, expects = numbered_parts(steps), numbered_parts(expected_results)
    if actions and expects and len(actions) == len(expects):
        pairs = [{"action": a, "expected": e} for a, e in zip(actions, expects, strict=True)]
    else:
        # Keep unmatched or unnumbered paragraphs together, never invent a pairing.
        pairs = (
            [{"action": steps, "expected": expected_results}] if steps or expected_results else []
        )
    return {
        "preconditions": numbered_parts(preconditions)
        or ([preconditions] if preconditions else []),
        "steps": pairs,
    }


def render_lines(values):
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "\n".join(f"{i}. {value}" for i, value in enumerate(values, 1))


def legacy_fields(content):
    return {
        "preconditions": render_lines(content.get("preconditions", [])),
        "steps": render_lines([s["action"] for s in content.get("steps", [])]),
        "expected_results": render_lines([s["expected"] for s in content.get("steps", [])]),
    }


def set_legacy_content(case, preconditions, steps, expected_results):
    case.content_json = from_legacy(preconditions, steps, expected_results)
    # Support existing import adapters that expose plain records rather than ORM properties.
    if not isinstance(getattr(type(case), "steps", None), property):
        case.preconditions, case.steps, case.expected_results = (
            preconditions,
            steps,
            expected_results,
        )
