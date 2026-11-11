#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from jsonschema import Draft202012Validator

schema = json.loads((Path(__file__).parent.parent / "schemas/profile.schema.json").read_text())
data = json.loads(Path(sys.argv[1]).read_text())
errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
if errors:
    for error in errors:
        print(f"{'.'.join(map(str, error.path)) or '$'}: {error.message}", file=sys.stderr)
    raise SystemExit(1)
print("valid")
