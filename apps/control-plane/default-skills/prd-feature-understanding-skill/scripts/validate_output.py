"""Check the bundled JSON Schema without altering the candidate or inferring facts."""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


def main():
    if len(sys.argv) != 2:
        print("Usage: python validate_output.py <candidate.json>")
        return 2
    try:
        candidate = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Cannot parse candidate: {type(exc).__name__}")
        return 1
    schema = json.loads((Path(__file__).resolve().parents[1] / "references/output-schema.json").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(candidate))
    for error in errors:
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        # Error values may contain full business text; return structure only.
        print(f"{path}: violates {error.validator}")
    quality_errors = []
    if not errors:
        for flow in candidate["businessFlows"]:
            for step in flow["steps"]:
                if not step["nextSteps"] and not (step.get("relatedQuestionIds") or flow.get("relatedQuestionIds")):
                    quality_errors.append(f"flow {flow['id']} / step {step['id']}: no successor or explicit end, and no linked unresolved question; connect the known continuation or remove a redundant flow")
    for message in quality_errors:
        print(message)
    print(f"Schema errors: {len(errors)}; flow quality errors: {len(quality_errors)}. Semantic/source review is still required.")
    return 1 if errors or quality_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
