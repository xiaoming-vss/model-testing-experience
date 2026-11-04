"""UI generation fixture payloads shared by tests; no collected cases."""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures/ui_generation"


def read(name):
    return json.loads((FIXTURES / (name + ".json")).read_text())
