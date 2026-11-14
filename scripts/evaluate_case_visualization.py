"""Evaluate human-reviewed visualization samples; never substitute model self-assessment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate(samples: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> dict[str, Any]:
    ids = {sample["id"] for sample in samples}
    reviewed = {review["id"]: review for review in reviews}
    if len(ids) != len(samples) or len(reviewed) != len(reviews):
        raise ValueError("Sample/review IDs must be unique")
    if set(reviewed) - ids:
        raise ValueError("Review references unknown sample")
    completed = []
    for sample_id in ids:
        review = reviewed.get(sample_id)
        if review is None:
            continue
        if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
            raise ValueError("Human reviewer is required")
        if type(review.get("suitable")) is not bool or type(review.get("usable")) is not bool:
            raise ValueError("Human suitability and usability judgments must be booleans")
        if type(review.get("severeErrorCount")) is not int or review["severeErrorCount"] < 0:
            raise ValueError("Severe error count must be a nonnegative integer")
        if not isinstance(review.get("evidence"), str) or not review["evidence"].strip():
            raise ValueError("Review must identify the generated output and key-fact evidence")
        completed.append(review)
    denominator = sum(r["suitable"] for r in completed)
    numerator = sum(r["suitable"] and r["usable"] and r["severeErrorCount"] == 0 for r in completed)
    severe = sum(r["severeErrorCount"] for r in completed)
    complete = len(samples) >= 50 and len(completed) == len(samples)
    ratio = numerator / denominator if denominator else None
    return {"passed": complete and severe == 0 and ratio is not None and ratio >= 0.8,
            "reviewComplete": complete, "sampleCount": len(samples), "reviewedCount": len(completed),
            "severeErrorCount": severe, "coverageNumerator": numerator,
            "coverageDenominator": denominator, "effectiveCoverage": ratio,
            "pendingSampleIds": sorted(ids - set(reviewed))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.samples.read_text()), json.loads(args.reviews.read_text()))
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(content)
    print(content)
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
