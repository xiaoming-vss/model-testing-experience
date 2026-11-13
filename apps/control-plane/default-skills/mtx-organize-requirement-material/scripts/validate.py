#!/usr/bin/env python3
"""Validate a readable requirement material JSON file (requires jsonschema)."""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from material_checks import validate_material as validate


def object_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result




def main():
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} <output.json>', file=sys.stderr)
        return 2
    schema = json.loads((Path(__file__).resolve().parent.parent / 'references/output.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    try:
        data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'), object_pairs_hook=object_no_duplicates)
    except (OSError, ValueError) as exc:
        print(f'INVALID: {exc}', file=sys.stderr)
        return 1
    errors = validate(data, schema)
    if errors:
        for error in errors:
            print(f'INVALID: {error}', file=sys.stderr)
        return 1
    print('VALID')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
