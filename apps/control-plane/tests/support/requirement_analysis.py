"""Shared requirement-analysis fixture readers; no collected tests."""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures/requirement_artifacts"


def example(name):
    return json.loads((FIXTURES / (name + ".example.json")).read_text())
