import copy
import json
from pathlib import Path

import pytest

from testing_agent.domain.case_visualization.contract import freeze_input, validate_artifact

EXAMPLES = json.loads(
    (
        Path(__file__).parents[1]
        / "default-skills/mtx-analyze-case-visualization/references/examples.json"
    ).read_text()
)


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda x: x["name"])
def test_four_shapes(example):
    assert validate_artifact(example["input"], example["output"]) == example["output"]


@pytest.mark.parametrize(
    "mutation",
    [
        "identity",
        "source",
        "expected",
        "relation",
        "local",
        "state",
        "unknown",
        "partial",
        "unsupported",
    ],
)
def test_invalid_outputs_rejected(mutation):
    example = copy.deepcopy(EXAMPLES[2])
    value = example["output"]
    if mutation == "identity":
        value["executionEntryId"] = "other"
    if mutation == "source":
        value["sources"][0]["index"] = 99
    if mutation == "expected":
        value["assertions"][0]["sourceIds"] = ["a0"]
    if mutation == "relation":
        value["relations"][0]["to"] = "missing"
    if mutation == "local":
        value["visuals"][0]["entityIds"] = ["save"]
    if mutation == "state":
        value["visuals"][0]["data"]["beforeEntityId"] = None
    if mutation == "unknown":
        value["visuals"][0]["html"] = "<script />"
    if mutation == "partial":
        value["status"] = "partial"
    if mutation == "unsupported":
        value["status"] = "unsupported"
    with pytest.raises(ValueError):
        validate_artifact(example["input"], value)


def test_partial_and_unsupported_and_empty_input():
    example = copy.deepcopy(EXAMPLES[0])
    value = example["output"]
    value["status"] = "partial"
    value["limitations"] = [{"reason": "部分检查未图解", "sourceIds": ["a0"]}]
    validate_artifact(example["input"], value)
    frozen = freeze_input("empty", {"preconditions": [], "steps": []})
    value = {
        "schemaVersion": "1.0",
        "executionEntryId": "empty",
        "status": "unsupported",
        "summary": {"text": None, "sourceIds": []},
        "sources": [],
        "entities": [],
        "relations": [],
        "assertions": [],
        "visuals": [],
        "limitations": [{"reason": "无可分析内容", "sourceIds": []}],
    }
    validate_artifact(frozen, value)


def test_snapshot_hash_keeps_order_and_empty_fields():
    first = freeze_input("a", {"preconditions": [], "steps": [{"action": "a", "expected": ""}]})
    second = freeze_input("a", {"steps": [{"expected": "", "action": "a"}], "preconditions": []})
    assert first == second
    assert first["sources"] == [{"id": "a0", "field": "action", "index": 0}]
    assert (
        freeze_input("a", {"preconditions": [], "steps": [{"action": " a", "expected": ""}]})[
            "snapshotHash"
        ]
        != first["snapshotHash"]
    )


def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError):
        validate_artifact(EXAMPLES[0]["input"], '{"status":"ready","status":"unsupported"}')
